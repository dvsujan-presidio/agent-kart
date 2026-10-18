"""AgentKart orchestrator: one brain for web chat and voice.

LLM = language only (nlu.py). Everything numeric comes from domain/. The only way to place an
order is approve() -> checkout(), which go through approval.ApprovalGate. No LLM tool reaches them.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from app import facts as facts_mod
from app import narrate
from app.approval import ApprovalError, ApprovalGate
from app.config import Settings
from app.converse import Converser, NullConverser
from app.nlu import NLU, NLUContext, TurnParse
from app.pipeline import PlanState, build_plan
from app.planner import Planner, store_menu, validate
from app.real_stores.mcp_client import McpError
from app.real_stores.service import REAL_ONLY, RealStoreService, build_plan_real
from app.session import Pending, Session
from app.ucp_client import StoreClient
from contracts.hashing import basket_hash
from contracts.models import Address, Approval, ApprovalRequest, Basket, BasketLine
from domain.fallback import find_fallback
from domain.optimizer import DEFAULT_BUFFER, _fee
from domain.quantities import load_template
from domain.split import split_equal

SUPPORTED = {"birthday_party"}


class CheckoutError(Exception):
    pass


@dataclass
class Reply:
    text: str  # deterministic text: used as-is when verbatim, else as the fallback for the LLM phrasing
    approval_request: ApprovalRequest | None = None
    situation: str = ""  # tells the conversation layer what this reply must do
    verbatim: bool = False  # approval read-backs are always spoken exactly as the server built them


def match_spec(specs: list, name: str) -> str | None:
    """Map a user's word ("the cooler", "tents") onto a planned item's category."""
    n = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    n1 = n.rstrip("s")
    for sp in specs:
        lab = re.sub(r"[^a-z0-9]+", "_", sp.label.lower()).strip("_")
        if n in (sp.category, lab) or n1 in (sp.category.rstrip("s"), lab.rstrip("s")):
            return sp.category
    for sp in specs:  # looser: one contains the other
        if n1 and (n1 in sp.category or sp.category.rstrip("s") in n or n1 in sp.label.lower()):
            return sp.category
    return None


def canonical_category(scenario: str, name: str) -> str:
    n = name.strip().lower()
    try:
        for t in load_template(scenario):
            if (
                n == t.category
                or n in t.aliases
                or n.rstrip("s") in {a.rstrip("s") for a in t.aliases}
            ):
                return t.category
    except KeyError:
        pass
    return n


class Orchestrator:
    def __init__(
        self,
        *,
        clients: list[StoreClient],
        nlu: NLU,
        gate: ApprovalGate,
        settings: Settings,
        clock: Callable[[], datetime] | None = None,
        converser: Converser | None = None,
        real: RealStoreService | None = None,
        planner: Planner | None = None,
    ):
        self.clients = {c.base_url: c for c in clients}
        self.nlu, self.gate, self.cfg = nlu, gate, settings
        self.converser = converser or NullConverser()
        self.real = real
        self.planner = planner
        self.tz = ZoneInfo(settings.default_timezone)
        self.clock = clock or (lambda: datetime.now(self.tz))

    # ------------------------------------------------------------------ chat
    async def handle_message(self, s: Session, text: str, channel: str | None = None) -> Reply:
        async with s.lock:
            if channel:
                s.channel = channel
            s.history.append({"role": "user", "content": text})
            await s.emit("chat_message", {"role": "user", "text": text, "channel": s.channel})
            ctx = NLUContext(
                now=self.clock(),
                timezone=self.cfg.default_timezone,
                last_question=s.last_question,
                has_basket=s.plan is not None,
                option_count=len(s.plan.options) if s.plan else 0,
                known={
                    "guests": s.state.guests,
                    "budget_minor": s.state.budget_minor,
                    "deadline": s.state.deadline.isoformat() if s.state.deadline else None,
                },
            )
            try:
                tp = await self.nlu.parse(s.history, ctx)
                reply = await self._apply(s, tp)
            except ApprovalError:
                raise
            except Exception as e:  # LLM/network failure must not corrupt state
                reply = Reply("Sorry, I had trouble with that. Could you say it again?")
                await s.emit("error", {"message": str(e)[:200]})
            reply = await self._phrase(s, reply)
            s.history.append({"role": "assistant", "content": reply.text})
            await s.emit("chat_message", {"role": "assistant", "text": reply.text})
            return reply

    GREETING = (
        "Hi, I'm AgentKart. Tell me what you're getting done, like a birthday party or a trip, "
        "and I'll plan it, budget it and order it across stores for you."
    )

    async def greet(self, s: Session) -> str:
        s.history.append({"role": "assistant", "content": self.GREETING})
        await s.emit("chat_message", {"role": "assistant", "text": self.GREETING, "greeting": True})
        return self.GREETING

    async def _phrase(self, s: Session, reply: Reply) -> Reply:
        """Let the LLM put the reply into natural words; Python still supplies every number."""
        if reply.verbatim or not reply.situation:
            return reply
        goal, facts, ph, desc = facts_mod.build(self, s, reply.situation)
        text = await self.converser.phrase(
            history=s.history,
            situation=reply.situation,
            goal=goal,
            facts=facts,
            placeholders=ph,
            descriptions=desc,
            channel=s.channel,
        )
        if text:
            reply.text = text
        return reply

    # -------------------------------------------------------------- state updates
    def _canon(self, st: PlanState, name: str) -> str:
        return match_spec(st.specs, name) or canonical_category(st.scenario, name)

    def _apply_updates(self, s: Session, tp: TurnParse) -> bool:
        st, changed = s.state, False

        def setv(obj, k, v):
            nonlocal changed
            if v is not None and (getattr(obj, k) if hasattr(obj, k) else obj.get(k)) != v:
                changed = True
                if hasattr(obj, k):
                    setattr(obj, k, v)
                else:
                    obj[k] = v

        if tp.scenario:
            setv(st, "scenario", tp.scenario)
        setv(st, "guests", tp.guests if tp.guests and tp.guests > 0 else None)
        if tp.budget_amount and tp.budget_amount > 0:
            setv(st, "budget_minor", round(tp.budget_amount * 100))
        if tp.deadline_iso:
            with contextlib.suppress(ValueError):
                d = datetime.fromisoformat(tp.deadline_iso)
                setv(st, "deadline", d if d.tzinfo else d.replace(tzinfo=self.tz))
        for e in tp.exclusions_add:
            c = self._canon(st, e)
            if c not in st.exclusions:
                st.exclusions.add(c)
                changed = True
        for e in tp.exclusions_remove:
            c = self._canon(st, e)
            if c in st.exclusions or c in st.dropped:
                st.exclusions.discard(c)
                st.dropped.discard(c)
                changed = True
        for e in tp.drop_categories:
            c = self._canon(st, e)
            if c not in st.dropped:
                st.dropped.add(c)
                changed = True
        setv(st.prefs, "cake_flavor", tp.cake_flavor.lower() if tp.cake_flavor else None)
        setv(st.prefs, "eggless", tp.eggless)
        setv(st.prefs, "cake_tier", tp.cake_tier)
        setv(st.prefs, "cake_kg", tp.cake_kg)
        if self._update_address(s, tp):
            self.gate.invalidate_session(s.id)  # an approval read-back named the old address
            if s.pending and s.pending.kind == "main":
                s.pending = None
        if tp.payers and tp.payers > 0:
            st.payers = tp.payers
        return changed

    def _saved_address(self) -> Address:
        c = self.cfg
        return Address(
            line1=c.saved_address_line1,
            area=c.saved_address_area,
            city=c.saved_address_city,
            pincode=c.saved_address_pincode,
        )

    @staticmethod
    def cart_json(c) -> dict:
        d = c.model_dump(mode="json")
        d["store_name"] = narrate.store_label(c.store_id)
        return d

    def _address_label(self, s: Session) -> str:
        """Short form for read-backs and questions."""
        a = s.address or self._saved_address()
        if a.area and a.city:
            return f"{a.area}, {a.city}"
        return a.area or a.line1

    def _address_full(self, s: Session) -> str:
        a = s.address or self._saved_address()
        parts = [a.line1] + ([a.area] if a.area and a.area not in a.line1 else []) + [a.city]
        return (", ".join(p for p in parts if p) + (f" {a.pincode}" if a.pincode else "")).strip()

    def _update_address(self, s: Session, tp: TurnParse) -> bool:
        """Conversational address capture: saved address, or a new one collected piece by piece."""
        if tp.use_saved_address:
            before = s.address
            s.address = self._saved_address()
            s.address_draft.clear()
            s.awaiting_address = False
            return before != s.address
        parts = {
            "line1": tp.address_text,
            "area": tp.address_area,
            "city": tp.address_city,
            "pincode": tp.address_pincode,
        }
        parts = {k: v.strip()[:200] for k, v in parts.items() if v and v.strip()}
        if tp.use_saved_address is False and not parts and "address" in s.asked:
            s.awaiting_address = True  # declined the saved address: ask for the new one
            s.address_draft.clear()
            return False
        if not parts:
            return False
        s.awaiting_address = True
        s.address_draft.update(parts)
        d = s.address_draft
        if "pincode" in d:
            digits = re.sub(r"\D", "", d["pincode"])
            if len(digits) == 6:
                d["pincode"] = digits
            else:
                d.pop("pincode")  # not a valid pincode: ask again
        if (d.get("line1") or d.get("area")) and d.get("pincode") and d.get("city"):
            s.address = Address(
                line1=d.get("line1") or d["area"],
                area=d.get("area"),
                city=d["city"],
                pincode=d["pincode"],
            )
            s.awaiting_address = False
            s.address_draft.clear()
            s.asked.add("address")
            return True
        return False

    def _next_question(self, s: Session) -> str | None:
        st = s.state
        for key, missing in (
            ("guests", st.guests is None),
            ("budget", st.budget_minor is None),
            ("deadline", st.deadline is None and st.needs_deadline),
        ):
            if missing:
                return key
        if self._is_real(s):
            return None  # real stores: no delivery address needed, you pay on the store's site
        if s.awaiting_address:
            d = s.address_draft
            if not (d.get("line1") or d.get("area")):
                return "address_new"
            if not d.get("pincode"):
                return "address_pincode"
            if not d.get("city"):
                return "address_city"
        optional = [
            ("cake_flavor", not st.prefs.get("cake_flavor")),
            ("eggless", st.prefs.get("eggless") is None),
            ("address", s.address is None),
        ]
        if len(s.asked & {k for k, _ in optional}) >= 3:
            return None
        for key, missing in optional:
            if missing and key not in s.asked:
                return key
        return None

    async def _ask(self, s: Session, key: str) -> Reply:
        s.asked.add(key)
        s.last_question = key
        return Reply(
            narrate.question_text(key, s.state, self._address_label(s)), situation=f"ask:{key}"
        )

    # ------------------------------------------------------------------ routing
    def _is_real(self, s: Session) -> bool:
        return s.state.currency == "USD"

    def _switch_mode(self, s: Session, scenario: str, real: bool) -> None:
        """Camping/apartment/gym -> real US stores (USD). Birthday -> demo stores (INR) unless the user
        asks for real ones. Keeps the head-count; budget currency changes so it is asked again."""
        old = s.state
        s.state = PlanState(
            scenario=scenario,
            currency="USD" if real else "INR",
            needs_deadline=not real,
            guests=old.guests,
            exclusions=set(old.exclusions),
            goal_text="",
            specs=[],
        )
        s.plan, s.pending, s.approval = None, None, None
        s.asked, s.last_question = set(), None
        s.real_carts = []
        self.gate.invalidate_session(s.id)

    async def _apply(self, s: Session, tp: TurnParse) -> Reply:
        want = (
            re.sub(r"[^a-z0-9]+", "_", tp.scenario.lower()).strip("_")
            if tp.scenario
            else s.state.scenario
        )
        if want != "birthday_party":
            want_real = True  # anything else is open-ended: planned dynamically for real stores
        else:
            want_real = tp.store_mode == "real" or (tp.store_mode is None and self._is_real(s))
            if tp.store_mode == "demo":
                want_real = False
        if not s.orders and (want != s.state.scenario or want_real != self._is_real(s)):
            if want_real and not (self.real and self.real.supports(want)):
                return Reply(
                    "Real Store Mode isn't enabled in this build, so I can only use the demo stores "
                    "for a birthday party right now.",
                    situation="unsupported",
                )
            self._switch_mode(s, want, want_real)
        if tp.goal_summary and self._is_real(s):
            s.state.goal_text = tp.goal_summary[:200]
        if self._is_real(s) and self.real and not self.real.available:
            return Reply(
                "To use real stores I need our public agent profile online first. Run "
                "scripts/start_profile.sh and try again.",
                situation="real_unavailable",
            )
        if s.orders and tp.intent in ("edit", "place_order", "apply_option", "provide_info"):
            if tp.intent == "place_order":
                return Reply(
                    "Your order is already placed. You can follow it in the tracker.",
                    situation="already_ordered",
                )
        changed = self._apply_updates(s, tp)
        if tp.add_items and self._is_real(s):
            changed = (await self._add_items(s, tp.add_items)) or changed
        s.last_question = None
        if s.awaiting_address and not self._is_real(s):
            q = self._next_question(s)
            if q and q.startswith("address_"):
                return await self._ask(s, q)
        nothing_yet = (
            s.plan is None
            and s.state.guests is None
            and s.state.budget_minor is None
            and s.state.deadline is None
            and not s.state.exclusions
        )
        if (
            nothing_yet
            and tp.scenario is None
            and tp.intent in ("other", "question", "provide_info")
            and not changed
        ):
            return Reply(self.GREETING, situation="greet")
        if tp.intent == "place_order":
            return await self._place_order(s)
        if tp.intent == "apply_option":
            return await self._apply_option(s, tp.option_index)
        if tp.intent == "split" and tp.payers and s.plan and not changed:
            return Reply(self._split_text(s), situation="split")
        if not s.state.ready():
            q = self._next_question(s)
            return await self._ask(s, q or "guests")
        q = self._next_question(s) if s.plan is None else None
        if q:
            return await self._ask(s, q)
        if s.plan is not None and not changed:
            if tp.intent == "split":
                return Reply(self._split_text(s), situation="split")
            return Reply(
                narrate.reply_plan(s.plan, s.state, self.clock(), s.channel),
                situation="plan_summary",
            )
        if s.address is None:
            s.address = self._saved_address()
        text = await self._replan(s)
        if tp.intent == "split" or s.state.payers > 1:
            if (
                s.plan
                and s.plan.basket.total_minor <= s.state.budget_minor
                and tp.intent == "split"
            ):
                text += " " + self._split_text(s)
        return Reply(text, situation=self._plan_situation(s, tp.intent == "split"))

    def _plan_situation(self, s: Session, split: bool = False) -> str:
        pr = s.plan
        if pr is None or pr.result.missing_required:
            return ""
        if split and pr.basket.total_minor <= s.state.budget_minor:
            return "split"
        return "over_budget" if pr.basket.total_minor > s.state.budget_minor else "plan_ready"

    def _split_text(self, s: Session) -> str:
        b = s.plan.basket
        shares = split_equal(b.total_minor, s.state.payers)
        return narrate.reply_split(b.total_minor, shares, b.currency, s.channel)

    async def _ensure_specs(self, s: Session) -> None:
        """Real stores: have the planner decide WHAT to buy for this request (once per goal)."""
        st = s.state
        if st.specs or not self.planner:
            return
        menu, ids, covers = store_menu(self.real.configs)
        goal = st.goal_text or st.scenario.replace("_", " ")
        try:
            plan = await self.planner.plan(goal, st.guests or 1, menu)
            st.specs = validate(plan, ids, covers)
            if st.specs:
                st.goal_text = st.goal_text or plan.title
        except Exception as e:
            await s.emit("error", {"message": f"planner: {str(e)[:150]}"})
        if not st.specs and st.scenario not in REAL_ONLY and st.scenario != "birthday_party":
            raise RuntimeError("I couldn't work out a shopping list for that")

    async def _add_items(self, s: Session, things: list[str]) -> bool:
        """'Add a tent': the planner turns each ask into a searchable item; sizing stays in Python."""
        st = s.state
        if not (things and self._is_real(s) and self.planner):
            return False
        await self._ensure_specs(s)
        menu, ids, covers = store_menu(self.real.configs)
        goal = st.goal_text or st.scenario.replace("_", " ")
        plan = await self.planner.plan(
            goal, st.guests or 1, menu, extra=things, existing=[sp.label for sp in st.specs]
        )
        have = {sp.category for sp in st.specs}
        new = [sp for sp in validate(plan, ids, covers) if sp.category not in have]
        for sp in new:
            st.dropped.discard(sp.category)
            st.exclusions.discard(sp.category)
        st.specs = st.specs + new
        return bool(new)

    async def _replan(self, s: Session) -> str:
        self.gate.invalidate_session(s.id)
        if s.pending and s.pending.kind == "main":
            s.pending = None
        if self._is_real(s):
            await self._ensure_specs(s)
            try:
                s.plan = await build_plan_real(s.state, self.real)
            except McpError as e:
                raise RuntimeError(f"Real stores are unreachable right now: {e}") from e
            s.real_carts = []
        else:
            s.plan = await build_plan(s.state, list(self.clients.values()))
        await s.emit("basket_updated", self.plan_view(s))
        return narrate.reply_plan(s.plan, s.state, self.clock(), s.channel)

    async def _apply_option(self, s: Session, idx: int | None) -> Reply:
        if not s.plan or not s.plan.options:
            return Reply("There are no options to apply right now.", situation="no_options")
        if idx is None and len(s.plan.options) == 1:
            idx = 1
        if idx is None or not 1 <= idx <= len(s.plan.options):
            return Reply(
                f"Which option? Say a number from 1 to {len(s.plan.options)}.",
                situation="clarify_option",
            )
        o = s.plan.options[idx - 1]
        st = s.state
        st.dropped |= o.dropped
        st.qty_overrides.update(o.resized)
        st.skip_stores |= o.skipped_stores
        st.prefs.update(o.prefs_update)
        text = await self._replan(s)
        return Reply(
            f"Done: {o.tradeoff.title.lower()}. {text}",
            situation="option_applied"
            if self._plan_situation(s) == "plan_ready"
            else self._plan_situation(s),
        )

    # ----------------------------------------------------------------- approval
    async def _real_handoff(self, s: Session) -> Reply:
        """Real stores: build one UCP cart per store and hand off. We never pay or check out."""
        b = s.plan.basket
        if s.plan.result.missing_required or not b.feasible:
            return Reply(
                "I can't build carts yet. "
                + narrate.reply_plan(s.plan, s.state, self.clock(), s.channel),
                situation="cannot_place",
            )
        s.real_carts = await self.real.build_carts(b)
        await s.emit("real_carts", {"carts": [self.cart_json(c) for c in s.real_carts]})
        names = [narrate.store_label(c.store_id) for c in s.real_carts]
        ok = [c for c in s.real_carts if c.handoff_url]
        text = (
            f"I've added everything to carts at {' and '.join(names)}. I haven't ordered anything: "
            "prices are estimates and shipping and tax are added at each store's own checkout. "
            + (
                "Use the Open cart buttons to review and pay there yourself."
                if ok
                else "I couldn't get cart links, so open each store to finish."
            )
        )
        return Reply(text, situation="real_handoff")

    async def _place_order(self, s: Session) -> Reply:
        if s.plan and self._is_real(s):
            return await self._real_handoff(s)
        if not s.plan or not s.state.ready():
            return Reply(
                "There's nothing to order yet. Tell me what you're planning first.",
                situation="nothing_to_order",
            )
        b = s.plan.basket
        if s.plan.result.missing_required or not b.feasible:
            return Reply(
                "I can't place this yet. "
                + narrate.reply_plan(s.plan, s.state, self.clock(), s.channel),
                situation="cannot_place",
            )
        if b.hash in s.ordered_hashes:
            return Reply("That order is already placed.", situation="already_ordered")
        if s.address is None:
            s.address = self._saved_address()
        text = narrate.readback(b, self._address_label(s), self.clock(), s.channel)
        req = self.gate.create_request(s.id, b.hash, text, self.clock())
        s.pending = Pending("main", b, req)
        await s.emit(
            "approval_requested",
            {
                "kind": "main",
                "request_id": req.request_id,
                "readback": text,
                "expires_at": req.expires_at.isoformat(),
                "basket": self.plan_view(s),
            },
        )
        return Reply(text, req, verbatim=True)

    def approve(
        self,
        s: Session,
        *,
        request_id: str,
        channel: str,
        utterance: str | None = None,
        stt_confidence: float | None = None,
    ) -> Approval:
        if s.pending is None or s.pending.request.request_id != request_id:
            raise ApprovalError("no matching approval request")
        a = self.gate.approve(
            session_id=s.id,
            request_id=request_id,
            current_basket_hash=self._current_hash(s),
            channel=channel,
            now=self.clock(),
            utterance=utterance,
            stt_confidence=stt_confidence,
        )
        s.approval = a
        return a

    def _current_hash(self, s: Session) -> str:
        """Hash of what would actually be bought right now (recomputed, never trusted from client)."""
        assert s.pending is not None
        if s.pending.kind == "main" and s.plan:
            return s.plan.basket.hash
        return basket_hash(s.pending.basket)

    async def announce_approved(self, s: Session, a: Approval) -> None:
        await s.emit(
            "approved",
            {
                "channel": a.channel,
                "at": a.approved_at.isoformat(),
                "kind": s.pending.kind if s.pending else "main",
            },
        )

    async def checkout(self, s: Session, token: str | None) -> list[dict]:
        async with s.lock:
            if s.pending is None:
                if s.approval and s.approval.basket_hash in s.ordered_hashes:
                    return s.orders  # idempotent: already placed
                raise ApprovalError("nothing awaiting checkout")
            pending = s.pending
            self.gate.verify(
                token, session_id=s.id, current_basket_hash=self._current_hash(s), now=self.clock()
            )
            basket = pending.basket
            by_store: dict[str, list[BasketLine]] = {}
            for ln in basket.lines:
                by_store.setdefault(ln.offer.store_id, []).append(ln)
            clients = {c.store_id: c for c in self.clients.values()}
            # 1. re-price every store first; abort before placing anything if any total moved
            for store, lines in by_store.items():
                cart = await clients[store].cart(
                    [{"variant_id": ln.offer.variant_id, "qty": ln.packs} for ln in lines]
                )
                expect = sum(ln.line_total_minor for ln in lines) + (
                    basket.fees_by_store.get(store) or 0
                )
                if cart["total_minor"] != expect:
                    raise CheckoutError(
                        f"{store} price changed ({cart['total_minor']} vs {expect})"
                    )
            # 2. place
            placed: list[dict] = []
            addr = (s.address or self._saved_address()).model_dump()
            for store, lines in by_store.items():
                o = await clients[store].checkout(
                    [{"variant_id": ln.offer.variant_id, "qty": ln.packs} for ln in lines],
                    addr,
                    pending.request.request_id,
                )
                rec = {
                    "order_id": o["order_id"],
                    "store_id": store,
                    "store_name": narrate.store_label(store),
                    "status": o["status"],
                    "eta": o["eta"],
                    "total_minor": o["total_minor"],
                    "items": [ln.offer.title for ln in lines],
                    "kind": pending.kind,
                    "replaces": pending.replaces_order,
                }
                placed.append(rec)
                s.orders.append(rec)
                await s.emit("order_status", rec)
            s.ordered_hashes.add(basket.hash)
            if pending.replaces_order:
                for o in s.orders:
                    if o["order_id"] == pending.replaces_order:
                        o["replaced"] = True
                        await s.emit("order_status", o)
            s.pending = None
            if s.tracker is None or s.tracker.done():
                s.tracker = asyncio.create_task(self._track(s))
            return placed

    # ------------------------------------------------------------------ tracker
    async def _track(self, s: Session) -> None:
        clients = {c.store_id: c for c in self.clients.values()}
        while True:
            await asyncio.sleep(self.cfg.track_interval_seconds)
            live = [o for o in s.orders if o["status"] != "delivered" and not o.get("replaced")]
            if not live:
                return
            for o in live:
                try:
                    fresh = await clients[o["store_id"]].order(o["order_id"])
                except Exception:
                    continue
                if fresh["status"] != o["status"] or fresh["eta"] != o["eta"]:
                    o["status"], o["eta"] = fresh["status"], fresh["eta"]
                    await s.emit("order_status", o)
                if (
                    o["kind"] == "main"
                    and s.state.deadline
                    and o["order_id"] not in s.fallback_done
                    and datetime.fromisoformat(o["eta"]) > s.state.deadline - DEFAULT_BUFFER
                ):
                    s.fallback_done.add(o["order_id"])
                    await self._fallback(s, o)

    async def _fallback(self, s: Session, order: dict) -> None:
        if not s.plan or s.state.deadline is None:
            return
        base = s.plan.basket
        lines = [ln for ln in base.lines if ln.offer.store_id == order["store_id"]]
        if not lines:
            return
        delayed = max(lines, key=lambda ln: ln.line_total_minor)
        offers = s.plan.fallback_offers + s.plan.offers
        fb = find_fallback(base, delayed, offers, s.plan.terms, deadline=s.state.deadline)
        store = narrate.store_label(order["store_id"])
        if fb is None:
            text = (
                f"Heads up: your order from {store} is delayed and I couldn't find a replacement "
                f"that arrives in time."
            )
            await s.emit("fallback", {"order_id": order["order_id"], "text": text, "option": None})
            await s.emit("chat_message", {"role": "assistant", "text": text})
            return
        o = fb.offer
        fee, _ = _fee(o.price_minor * fb.packs, s.plan.terms.get(o.store_id))
        mini = Basket(
            lines=[BasketLine(offer=o, packs=fb.packs, line_total_minor=o.price_minor * fb.packs)],
            fees_by_store={o.store_id: fee},
            total_minor=fb.cost_minor,
            budget_minor=base.budget_minor,
            currency=base.currency,
            feasible=fb.within_budget,
            hash="",
        )
        mini = mini.model_copy(update={"hash": basket_hash(mini)})
        cur = base.currency
        extra = (
            f" That's {narrate.say_money(abs(fb.extra_minor), cur, s.channel)} "
            f"{'more' if fb.extra_minor >= 0 else 'less'} than the delayed item, "
            f"{'still within' if fb.within_budget else 'over'} your budget."
        )
        rb = narrate.readback(mini, "", self.clock(), s.channel, kind="backup", extra=extra)
        req = self.gate.create_request(s.id, mini.hash, rb, self.clock())
        s.pending = Pending("backup", mini, req, replaces_order=order["order_id"])
        text = f"Heads up: your {delayed.offer.title} from {store} is delayed. {rb}"
        await s.emit(
            "fallback",
            {
                "order_id": order["order_id"],
                "text": text,
                "option": {
                    "store_id": o.store_id,
                    "title": o.title,
                    "extra_minor": fb.extra_minor,
                    "cost_minor": fb.cost_minor,
                    "within_budget": fb.within_budget,
                },
            },
        )
        await s.emit("chat_message", {"role": "assistant", "text": text, "fallback": True})
        await s.emit(
            "approval_requested",
            {
                "kind": "backup",
                "request_id": req.request_id,
                "readback": rb,
                "announce": text,
                "expires_at": req.expires_at.isoformat(),
                "basket": self._basket_json(mini, s),
            },
        )

    async def demo_delay(self, s: Session, store_id: str = "cakecorner", hours: float = 24) -> dict:
        clients = {c.store_id: c for c in self.clients.values()}
        order = next(
            (o for o in s.orders if o["store_id"] == store_id and o["kind"] == "main"), None
        )
        if order is None:
            raise CheckoutError(f"no {store_id} order to delay")
        fresh = await clients[store_id].delay(order["order_id"], hours)
        order["status"], order["eta"] = fresh["status"], fresh["eta"]
        await s.emit("order_status", order)
        if s.tracker is None or s.tracker.done():
            s.tracker = asyncio.create_task(self._track(s))
        return order

    # --------------------------------------------------------------------- views
    def _basket_json(self, b: Basket, s: Session) -> dict:
        deadline = s.state.deadline
        return {
            "hash": b.hash,
            "currency": b.currency,
            "total_minor": b.total_minor,
            "budget_minor": b.budget_minor,
            "feasible": b.feasible,
            "estimate": b.total_is_estimate,
            "fees": {k: v for k, v in b.fees_by_store.items()},
            "lines": [
                {
                    "store_id": ln.offer.store_id,
                    "store_name": narrate.store_label(ln.offer.store_id),
                    "title": ln.offer.title,
                    "category": ln.offer.category,
                    "packs": ln.packs,
                    "unit_price_minor": ln.offer.price_minor,
                    "line_total_minor": ln.line_total_minor,
                    "eta": ln.offer.eta.isoformat() if ln.offer.eta else None,
                    "image_url": ln.offer.attributes.get("image_url") or None,
                    "url": ln.offer.url,
                    "on_time": bool(
                        ln.offer.eta and deadline and ln.offer.eta <= deadline - DEFAULT_BUFFER
                    ),
                }
                for ln in b.lines
            ],
        }

    def plan_view(self, s: Session) -> dict | None:
        pr = s.plan
        if pr is None:
            return None
        st, b = s.state, pr.basket
        rules = {i.category: i.rule for i in pr.items}
        view = self._basket_json(b, s)
        for ln in view["lines"]:
            ln["rule"] = rules.get(ln["category"], "")
        view.update(
            {
                "deadline": st.deadline.isoformat() if st.deadline else None,
                "excluded": [
                    {
                        "store_name": narrate.store_label(e.offer.store_id),
                        "title": e.offer.title,
                        "reason": e.reason,
                        "eta": e.offer.eta.isoformat() if e.offer.eta else None,
                    }
                    for e in b.excluded
                ],
                "late_notes": [
                    {
                        "store_name": narrate.store_label(n.store_id),
                        "category": n.category,
                        "cheaper_by_minor": n.cheaper_by_minor,
                        "eta": n.eta.isoformat(),
                    }
                    for n in pr.late_notes
                ],
                "options": [
                    {
                        "index": i,
                        "title": o.tradeoff.title,
                        "delta_minor": o.tradeoff.delta_minor,
                        "new_total_minor": o.tradeoff.basket.total_minor,
                        "within_budget": o.tradeoff.basket.total_minor <= st.budget_minor,
                    }
                    for i, o in enumerate(pr.options, 1)
                ],
                "insight": (
                    {
                        "saving_minor": pr.insight.saving_minor,
                        "optimal_stores": pr.insight.optimal_stores,
                        "naive_stores": pr.insight.naive_stores,
                    }
                    if pr.insight and pr.insight.saving_minor > 0
                    else None
                ),
                "payers": st.payers,
                "shares_minor": split_equal(b.total_minor, st.payers) if st.payers > 1 else None,
                "missing_required": pr.result.missing_required,
                "notes": pr.notes,
                "guests": st.guests,
                "mode": "real" if self._is_real(s) else "demo",
                "real_carts": [self.cart_json(c) for c in s.real_carts],
                "address": self._address_full(s) if s.address and not self._is_real(s) else None,
            }
        )
        return view

    def summary(self, s: Session) -> dict:
        pr = s.plan
        link = f"{self.cfg.web_url}/review/{s.id}"
        if pr is None:
            return {"text": "No plan yet.", "review_url": link}
        b = pr.basket
        text = (
            f"{len(b.lines)} items from {narrate.n_stores(b)} stores, total "
            f"{narrate.money(b.total_minor, b.currency)} of {narrate.money(b.budget_minor, b.currency)} budget. "
            f"Review and approve: {link}"
        )
        return {
            "text": text,
            "review_url": link,
            "total_minor": b.total_minor,
            "currency": b.currency,
            "stores": narrate.n_stores(b),
            "excluded": len(b.excluded),
        }
