"""Real Store Mode: search -> select -> cart -> handoff, over UCP/MCP, USD, never pays.

Each step degrades gracefully and records why; the optimizer is the same deterministic code used for
the demo stores (fees are unknown here, so baskets are flagged as estimates).
"""

from __future__ import annotations

import asyncio
import math
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import yaml

from app.pipeline import Option, PlanResult, PlanState, build_items
from app.real_stores.mcp_client import McpError, McpStore
from contracts.models import Basket, BasketLine, ListItem, Offer, RealCart, StoreTerms
from domain.optimizer import fee_insight, optimize
from domain.tradeoffs import tradeoff_plans

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
REAL_SCENARIOS = ("camping_weekend", "first_apartment", "home_gym", "birthday_party")
REAL_ONLY = ("camping_weekend", "first_apartment", "home_gym")  # no demo-store catalog for these


def _clean(s: str, n: int = 120) -> str:
    return "".join(ch if ch.isprintable() and ch not in "<>`" else " " for ch in str(s)).strip()[:n]


def load_store_config(path: Path | None = None) -> dict[str, dict]:
    raw = yaml.safe_load((path or ROOT / "config" / "real_stores.yaml").read_text())
    out: dict[str, dict] = {}
    for sc in raw["scenarios"].values():
        for s in sc["stores"]:
            if s.get("enabled", True):
                out.setdefault(s["id"], s)
    return out


def load_queries() -> dict:
    return yaml.safe_load((HERE / "queries.yaml").read_text())


_PACK = [
    re.compile(r"(\d{1,3})\s*[- ]?(?:ct|count|pk|pcs|pieces?|cans?|bottles?)\b", re.I),
    re.compile(r"(\d{1,3})\s*[- ]?pack\b", re.I),
    re.compile(r"(?:pack|set|box|bundle) of (\d{1,3})\b", re.I),
]


# Seasonal / licensed-character items are poor defaults for a generic plan.
AVOID = (
    "cocomelon",
    "holiday",
    "christmas",
    "halloween",
    "valentine",
    "easter",
    "thanksgiving",
    "snowflake",
    "bluey",
    "hot wheels",
    "lego",
    "marvel",
    "avengers",
    "star wars",
    "transformers",
    "sonic",
    "minecraft",
    "trolls",
    "encanto",
    "moana",
    "paw patrol",
    "disney",
    "mickey",
    "minnie",
    "frozen",
    "mario",
    "pokemon",
    "spiderman",
    "barbie",
    "hello kitty",
    "peppa",
    "sesame",
    "gabby",
    "baby shark",
    "unicorn",
)


def parse_pack_size(title: str) -> int:
    """'Paper Cups (8ct)' -> 8, '12 Pack' -> 12, 'Set of 2' -> 2; default 1 (a single item)."""
    for rx in _PACK:
        m = rx.search(title)
        if m and int(m.group(1)) >= 1:
            return int(m.group(1))
    return 1


def real_items(st: PlanState) -> list[ListItem]:
    """Shopping list for real stores: same deterministic quantities, restated in pieces where the
    template used grams/millilitres (real catalogs sell cakes, cans and bags by the piece)."""
    if st.specs:  # planner-built list: rules from the model, arithmetic here
        from app.planner import items_for

        gone = {*st.exclusions, *st.dropped}
        items = items_for([sp for sp in st.specs if sp.category not in gone], st.guests or 1)
        out_items = []
        for it in items:
            q = st.qty_overrides.get(it.category)
            if q is not None:
                it = it.model_copy(
                    update={"need_qty": float(q), "rule": f"{it.rule}; set to {q:g}"}
                )
            out_items.append(it)
        return out_items
    items = build_items(st)
    over = load_queries().get("_units", {}).get(st.scenario, {})
    out = []
    for it in items:
        o = over.get(it.category)
        if not o:
            out.append(it)
            continue
        guests = st.guests or 1
        qty = math.ceil(o["fixed"]) if "fixed" in o else math.ceil(guests * o["per_guest"])
        rule = (
            f"{o['fixed']} {o['label']} per order = {qty}"
            if "fixed" in o
            else f"{guests} guests x {o['per_guest']} {o['label']} = {qty}"
        )
        out.append(it.model_copy(update={"need_qty": float(qty), "unit": "pcs", "rule": rule}))
    return out


def offers_from_products(
    store: McpStore,
    category: str,
    products: list[dict],
    keywords: list[str],
    per_store: int = 3,
    avoid: list[str] | None = None,
) -> list[Offer]:
    """Normalize UCP catalog products into Offers: cheapest available variant per product."""
    offers: list[Offer] = []
    for p in products:
        title = _clean(p.get("title", ""))
        low = title.lower()
        extra_avoid = [a.lower() for a in (avoid or [])]
        if not any(k.lower() in low for k in keywords) or any(
            a in low for a in (*AVOID, *extra_avoid)
        ):
            continue  # semantic search returns neighbours; keep only on-topic, generic products
        variants = [v for v in p.get("variants", []) if v.get("availability", {}).get("available")]
        if not variants:
            continue
        v = min(variants, key=lambda x: x.get("price", {}).get("amount", 10**12))
        price = v.get("price", {})
        if "amount" not in price or price.get("currency") != "USD":
            continue
        vt = _clean(v.get("title", ""))
        full_title = title + (f" ({vt})" if vt and vt.lower() != "default title" else "")
        media = (v.get("media") or p.get("media") or [{}])[0]
        offers.append(
            Offer(
                store_id=store.store_id,
                source="ucp_real",
                product_id=p["id"],
                variant_id=v["id"],
                title=title + (f" ({vt})" if vt and vt.lower() != "default title" else ""),
                category=category,
                pack_size=parse_pack_size(full_title),
                unit="pcs",
                price_minor=int(price["amount"]),
                currency="USD",
                rating=None,
                eta=None,
                in_stock=True,
                url=p.get("url"),
                attributes={"image_url": media.get("url", ""), "store_domain": store.domain},
            )
        )
        if len(offers) >= per_store:
            break
    return offers


class RealStoreService:
    def __init__(self, cfg, http: httpx.AsyncClient):
        self.cfg = cfg
        self.http = http
        self.queries = load_queries()
        self.configs = load_store_config()
        self.stores = {
            sid: McpStore(
                sid,
                s["domain"],
                http,
                self.profile_url,
                replay=cfg.real_store_replay,
                record=cfg.real_store_record,
            )
            for sid, s in load_store_config().items()
        }

    def profile_url(self) -> str | None:
        return self.cfg.agent_profile_url

    @property
    def available(self) -> bool:
        return bool(
            self.cfg.real_store_mode
            and self.cfg.real_store_search
            and (self.profile_url() or self.cfg.real_store_replay)
        )

    def supports(self, scenario: str) -> bool:
        return self.cfg.real_store_mode and (
            scenario not in REAL_SCENARIOS  # open-ended job: planned dynamically
            or scenario in {x.strip() for x in self.cfg.real_store_scenarios.split(",")}
        )

    async def source(
        self, scenario: str, items: list[ListItem], specs: list | None = None
    ) -> tuple[dict[str, StoreTerms], list[Offer], list[str]]:
        if specs:  # dynamic plan from the planner
            plan = {
                sp.category: {
                    "stores": sp.stores,
                    "query": sp.query,
                    "keywords": sp.keywords,
                    "avoid": sp.avoid,
                }
                for sp in specs
            }
        else:  # curated fallback for the built-in scenarios
            plan = {k: v for k, v in self.queries.get(scenario, {}).items()}
        jobs: list[tuple[McpStore, str, dict]] = []
        for it in items:
            q = plan.get(it.category)
            for sid in (q or {}).get("stores", []):
                if sid in self.stores:
                    jobs.append((self.stores[sid], it.category, q))

        async def run(store: McpStore, cat: str, q: dict):
            return offers_from_products(
                store, cat, await store.search(q["query"]), q["keywords"], avoid=q.get("avoid")
            )

        results = await asyncio.gather(*(run(*j) for j in jobs), return_exceptions=True)
        offers: list[Offer] = []
        notes: list[str] = []
        failed: set[str] = set()
        for (store, _cat, _q), r in zip(jobs, results, strict=True):
            if isinstance(r, Exception):
                failed.add(store.store_id)
            else:
                offers.extend(r)
        asked = {j[0].store_id for j in jobs}
        if jobs and failed >= asked and not offers:
            profile_down = any(
                isinstance(r, McpError) and "profile" in f"{r.code} {r.data}" for r in results
            )
            raise McpError(
                "unreachable",
                "the stores rejected us because our agent profile isn't reachable (restart the "
                "tunnel with scripts/start_profile.sh)"
                if profile_down
                else "none of the real stores responded",
            )
        for sid in sorted(failed):
            notes.append(f"{sid} didn't respond, so I skipped it")
        terms = {sid: StoreTerms(store_id=sid) for sid in {o.store_id for o in offers}}
        return terms, offers, notes

    async def build_carts(self, basket: Basket) -> list[RealCart]:
        by_store: dict[str, list[BasketLine]] = {}
        for ln in basket.lines:
            by_store.setdefault(ln.offer.store_id, []).append(ln)

        async def one(sid: str, lines: list[BasketLine]) -> RealCart:
            store = self.stores[sid]
            expected = sum(ln.line_total_minor for ln in lines)
            degraded: list[str] = []
            cart: dict | None = None
            if self.cfg.real_store_cart:
                try:
                    cart = await store.create_cart(
                        [{"variant_id": ln.offer.variant_id, "quantity": ln.packs} for ln in lines]
                    )
                except McpError:
                    degraded.append("cart_failed_showing_search_prices")
            else:
                degraded.append("cart_disabled_showing_search_prices")
            subtotal, url = expected, None
            if cart:
                tot = {t["type"]: t["amount"] for t in cart.get("totals", []) if "amount" in t}
                subtotal = tot.get("subtotal", tot.get("total", expected))
                if subtotal != expected:
                    degraded.append("price_differs_from_search")
                url = cart.get("continue_url") if self.cfg.real_store_handoff else None
            if cart and not url and self.cfg.real_store_handoff:
                degraded.append("no_handoff_url")
            return RealCart(
                store_id=sid,
                store_domain=store.domain,
                ucp_cart_id=(cart or {}).get("id"),
                lines=lines,
                subtotal_minor=subtotal,
                shipping_estimate_minor=None,
                currency="USD",
                handoff_url=url,
                handoff_kind="cart_continue_url" if url else None,
                degraded=degraded,
            )

        return list(await asyncio.gather(*(one(s, ls) for s, ls in by_store.items())))


async def build_plan_real(st: PlanState, svc: RealStoreService) -> PlanResult:
    items = real_items(st)
    terms, offers, notes = await svc.source(st.scenario, items, st.specs)
    live = [o for o in offers if o.store_id not in st.skip_stores]
    have = {o.category for o in live}
    labels = {sp.category: sp.label for sp in st.specs}
    missing = [it for it in items if it.category not in have]
    if missing:  # not stocked at the stores asked: say so and plan the rest
        notes.append(
            "I couldn't find in stock: "
            + ", ".join(labels.get(m.category, m.category.replace("_", " ")) for m in missing)
        )
        items = [it for it in items if it.category in have]
    far = datetime.now(ZoneInfo("Asia/Kolkata")) + timedelta(days=365)  # real ETAs are unknown
    kw = dict(
        budget_minor=st.budget_minor,
        currency="USD",
        deadline=st.deadline or far,
        exclusions=sorted(st.exclusions),
    )
    result = optimize(items, live, terms, **kw)
    if not items:
        result.missing_required = ["anything for this request"]
    insight = fee_insight(
        items, live, terms, currency="USD", deadline=kw["deadline"], exclusions=kw["exclusions"]
    )
    options: list[Option] = []
    if not result.missing_required and result.basket.total_minor > st.budget_minor:
        for p in tradeoff_plans(items, live, terms, base=result.basket, **kw):
            options.append(Option(p.tradeoff, p.dropped, p.resized, p.skipped_stores))
    notes.append("Prices come live from each store; shipping and tax are added at their checkout.")
    return PlanResult(items, result, options[:3], insight, [], notes, live, [], terms)
