"""Deterministic planning pipeline: goal state -> list -> offers -> basket -> options.

No LLM here. Every number comes from domain/.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.ucp_client import StoreClient
from contracts.models import Basket, ListItem, Offer, StoreTerms, TradeOff
from domain.optimizer import DEFAULT_BUFFER, FeeInsight, OptimizeResult, fee_insight, optimize
from domain.quantities import packs_needed, plan_list
from domain.tradeoffs import tradeoff_plans


@dataclass
class PlanState:
    """Everything the user has decided so far. The single source for (re)planning."""

    scenario: str = "birthday_party"
    guests: int | None = None
    budget_minor: int | None = None
    deadline: datetime | None = None
    currency: str = "INR"
    exclusions: set[str] = field(default_factory=set)  # things the user already has
    dropped: set[str] = field(default_factory=set)  # dropped by an applied trade-off
    qty_overrides: dict[str, float] = field(default_factory=dict)
    skip_stores: set[str] = field(default_factory=set)
    prefs: dict = field(default_factory=dict)  # cake_flavor, eggless, cake_tier, cake_kg
    payers: int = 1
    needs_deadline: bool = True  # real stores have no ETAs, so the deadline is optional there
    goal_text: str = ""  # the job in the user's words (drives dynamic planning on real stores)
    specs: list = field(
        default_factory=list
    )  # planner.ItemSpec list for open-ended real-store jobs

    def ready(self) -> bool:
        need = (self.guests, self.budget_minor) + ((self.deadline,) if self.needs_deadline else ())
        return None not in need


@dataclass
class Option:
    tradeoff: TradeOff
    dropped: set[str] = field(default_factory=set)
    resized: dict[str, float] = field(default_factory=dict)
    skipped_stores: set[str] = field(default_factory=set)
    prefs_update: dict = field(default_factory=dict)


@dataclass
class LateNote:
    store_id: str
    category: str
    title: str
    cheaper_by_minor: int
    eta: datetime


@dataclass
class PlanResult:
    items: list[ListItem]
    result: OptimizeResult
    options: list[Option]
    insight: FeeInsight | None
    late_notes: list[LateNote]
    notes: list[str]
    offers: list[Offer]  # primary (deliverable) offers
    fallback_offers: list[Offer]  # pickup-only offers, used only by the tracker's fallback
    terms: dict[str, StoreTerms]

    @property
    def basket(self) -> Basket:
        return self.result.basket


async def source(clients: list[StoreClient]) -> tuple[dict[str, StoreTerms], list[Offer]]:
    results = await asyncio.gather(*(c.search() for c in clients), return_exceptions=True)
    terms: dict[str, StoreTerms] = {}
    offers: list[Offer] = []
    for r in results:
        if isinstance(r, Exception):
            continue  # a store that is down simply contributes nothing
        t, o = r
        terms[t.store_id] = t
        offers.extend(o)
    return terms, offers


def filter_prefs(offers: list[Offer], prefs: dict, notes: list[str]) -> list[Offer]:
    """Apply cake preferences (flavor / eggless / tier). Relax flavor if nothing matches."""
    tier = prefs.get("cake_tier") or "standard"
    flavor = (prefs.get("cake_flavor") or "").lower() or None
    eggless = bool(prefs.get("eggless"))

    def ok(o: Offer, use_flavor: bool) -> bool:
        a = o.attributes
        return (
            (not use_flavor or not flavor or a.get("flavor") == flavor)
            and (not eggless or a.get("eggless") is True)
            and a.get("tier", tier) == tier
        )

    cakes = [o for o in offers if o.category == "cake"]
    rest = [o for o in offers if o.category != "cake"]
    keep = [o for o in cakes if ok(o, True)]
    if flavor and not keep:
        keep = [o for o in cakes if ok(o, False)]
        notes.append(f"No {flavor} cake available, showing other flavors")
    return rest + keep


def _late_notes(plan_items: list[ListItem], basket: Basket) -> list[LateNote]:
    by_cat = {ln.offer.category: ln for ln in basket.lines}
    items = {i.category: i for i in plan_items}
    notes: list[LateNote] = []
    seen: set[tuple[str, str]] = set()
    for ex in basket.excluded:
        if ex.reason != "late" or ex.offer.category not in by_cat:
            continue
        item, chosen, o = items[ex.offer.category], by_cat[ex.offer.category], ex.offer
        packs = packs_needed(item.need_qty, item.unit, o.pack_size, o.unit)
        if packs is None or o.eta is None:
            continue
        cheaper = chosen.line_total_minor - o.price_minor * packs
        key = (o.store_id, o.category)
        if cheaper > 0 and key not in seen:
            seen.add(key)
            notes.append(LateNote(o.store_id, o.category, o.title, cheaper, o.eta))
    return sorted(notes, key=lambda n: -n.cheaper_by_minor)


def build_items(st: PlanState) -> list[ListItem]:
    items = plan_list(
        st.scenario,
        st.guests or 1,
        sorted(st.exclusions | st.dropped),
        {"beds": st.prefs.get("beds", 1)},
    )
    out = []
    for it in items:
        q = st.qty_overrides.get(it.category)
        if q is None and it.category == "cake" and st.prefs.get("cake_kg"):
            q = float(st.prefs["cake_kg"]) * 1000
        if q is not None:
            it = it.model_copy(
                update={"need_qty": float(q), "rule": f"{it.rule}; set to {q:g} {it.unit}"}
            )
        out.append(it)
    return out


async def build_plan(
    st: PlanState, clients: list[StoreClient], *, buffer: timedelta = DEFAULT_BUFFER
) -> PlanResult:
    assert st.ready(), "plan state incomplete"
    terms, all_offers = await source(clients)
    notes: list[str] = []
    live = [o for o in all_offers if not o.pickup_only and o.store_id not in st.skip_stores]
    fallback = [o for o in all_offers if o.pickup_only]
    live = filter_prefs(live, st.prefs, notes)
    items = build_items(st)
    kw = dict(
        budget_minor=st.budget_minor,
        currency=st.currency,
        deadline=st.deadline,
        buffer=buffer,
        exclusions=sorted(st.exclusions),
    )
    result = optimize(items, live, terms, **kw)
    insight = fee_insight(
        items,
        live,
        terms,
        currency=st.currency,
        deadline=st.deadline,
        buffer=buffer,
        exclusions=sorted(st.exclusions),
    )
    options: list[Option] = []
    if not result.missing_required and result.basket.total_minor > st.budget_minor:
        for p in tradeoff_plans(items, live, terms, base=result.basket, **kw):
            options.append(Option(p.tradeoff, p.dropped, p.resized, p.skipped_stores))
        if (st.prefs.get("cake_tier") or "standard") == "premium":
            std_prefs = {**st.prefs, "cake_tier": "standard"}
            std_live = filter_prefs(
                [o for o in all_offers if not o.pickup_only and o.store_id not in st.skip_stores],
                std_prefs,
                [],
            )
            r2 = optimize(items, std_live, terms, **kw)
            delta = r2.basket.total_minor - result.basket.total_minor
            if not r2.missing_required and delta < 0:
                swap = Option(
                    TradeOff(
                        title="Use a standard cake instead of premium",
                        delta_minor=delta,
                        basket=r2.basket,
                    ),
                    prefs_update={"cake_tier": "standard"},
                )
                if r2.basket.total_minor <= st.budget_minor:
                    options.insert(0, swap)
                else:
                    options.append(swap)
        options = options[:3]
    return PlanResult(
        items,
        result,
        options,
        insight,
        _late_notes(items, result.basket),
        notes,
        live,
        fallback,
        terms,
    )
