"""Deterministic reply text. Every number is formatted from domain output, never invented."""

from __future__ import annotations

from datetime import datetime

from app.pipeline import PlanResult, PlanState
from contracts.models import Basket
from voice.speech_format import speak_money, speak_time


def money(minor: int, currency: str = "INR") -> str:
    major, minor_part = divmod(abs(minor), 100)
    sign = "-" if minor < 0 else ""
    if currency == "INR":
        s = f"{major:,}"
        if major >= 1000:  # Indian grouping: 12,34,567
            head, tail = str(major)[:-3], str(major)[-3:]
            groups = []
            while len(head) > 2:
                groups.insert(0, head[-2:])
                head = head[:-2]
            if head:
                groups.insert(0, head)
            s = ",".join(groups + [tail])
        return f"{sign}₹{s}" + (f".{minor_part:02d}" if minor_part else "")
    return f"{sign}${major:,}.{minor_part:02d}"


def say_money(minor: int, currency: str, channel: str) -> str:
    return speak_money(minor, currency) if channel == "voice" else money(minor, currency)


def n_stores(b: Basket) -> int:
    return len({ln.offer.store_id for ln in b.lines})


def latest_eta(b: Basket) -> datetime | None:
    etas = [ln.offer.eta for ln in b.lines if ln.offer.eta]
    return max(etas) if etas else None


_REAL_NAMES: dict[str, str] | None = None


def _real_names() -> dict[str, str]:
    global _REAL_NAMES
    if _REAL_NAMES is None:
        try:
            from app.real_stores.service import load_store_config

            _REAL_NAMES = {sid: c["name"] for sid, c in load_store_config().items()}
        except Exception:
            _REAL_NAMES = {}
    return _REAL_NAMES


def store_label(store_id: str) -> str:
    demo = {
        "cakecorner": "CakeCorner",
        "snackmart": "SnackMart",
        "partybazaar": "PartyBazaar",
        "nearbybakery": "NearbyBakery",
    }
    return demo.get(store_id) or _real_names().get(store_id, store_id)


def question_text(key: str, st: PlanState, area: str) -> str:
    return {
        "guests": "How many people is this for?",
        "budget": "What's your budget?",
        "deadline": "When do you need everything by?",
        "cake_flavor": "What cake flavor would you like?",
        "eggless": "Should the cake be eggless?",
        "address": f"Should I deliver to your saved address in {area}?",
        "address_new": "Sure. What address should I deliver to?",
        "address_pincode": "Got it. What's the pincode for that address?",
        "address_city": "And which city is that in?",
    }[key]


def reply_plan(pr: PlanResult, st: PlanState, now: datetime, channel: str) -> str:
    b, cur = pr.basket, st.currency
    parts: list[str] = []
    if pr.result.missing_required:
        cats = ", ".join(c.replace("_", " ") for c in pr.result.missing_required)
        return (
            f"I couldn't find anything that arrives in time for: {cats}. "
            "Try a later deadline or a different request."
        )
    over = b.total_minor - b.budget_minor
    if over > 0:
        parts.append(
            f"That comes to {say_money(b.total_minor, cur, channel)}, "
            f"{say_money(over, cur, channel)} over your {say_money(b.budget_minor, cur, channel)} budget."
        )
        parts.append(reply_options(pr, st, channel))
        return " ".join(p for p in parts if p)
    left = b.budget_minor - b.total_minor
    stores = n_stores(b)
    if channel == "voice":
        parts.append(
            f"Your basket is {say_money(b.total_minor, cur, channel)} from {stores} "
            f"store{'s' if stores != 1 else ''}, {say_money(left, cur, channel)} under budget."
        )
    else:
        parts.append(
            f"Here's the plan: {len(b.lines)} items from {stores} store{'s' if stores != 1 else ''} "
            f"for {money(b.total_minor, cur)} including delivery "
            f"({money(left, cur)} left of your {money(b.budget_minor, cur)} budget)."
        )
    ins = pr.insight
    if ins and ins.saving_minor > 0 and ins.optimal_stores < ins.naive_stores:
        parts.append(
            f"Using {ins.optimal_stores} stores instead of {ins.naive_stores} saved "
            f"{say_money(ins.saving_minor, cur, channel)}."
        )
    for n in pr.late_notes[:1]:
        parts.append(
            f"{store_label(n.store_id)} {n.category.replace('_', ' ')} would be "
            f"{say_money(n.cheaper_by_minor, cur, channel)} cheaper but arrives "
            f"{speak_time(n.eta, now).split(' ', 2)[-1]}, so I excluded it."
        )
    parts.extend(pr.notes)
    if st.exclusions:
        parts.append("I left out " + ", ".join(sorted(st.exclusions)) + " since you have them.")
    if b.total_is_estimate:
        parts.append("Some delivery fees are unknown, so this total is an estimate.")
    parts.append("Say 'place the order' when you're ready.")
    return " ".join(parts)


def reply_options(pr: PlanResult, st: PlanState, channel: str) -> str:
    cur = st.currency
    if not pr.options:
        return (
            "I couldn't find a cheaper alternative. Try raising the budget or dropping something."
        )
    if channel == "voice":
        o = pr.options[0]
        within = o.tradeoff.basket.total_minor <= st.budget_minor
        tail = "That brings you under budget." if within else "That helps but is still over."
        more = f" I've put {len(pr.options) - 1} more on screen." if len(pr.options) > 1 else ""
        return (
            f"Option one: {o.tradeoff.title.lower()}, saving "
            f"{say_money(-o.tradeoff.delta_minor, cur, channel)}. {tail}{more} Want option one?"
        )
    lines = []
    for i, o in enumerate(pr.options, 1):
        t = o.tradeoff
        flag = "" if t.basket.total_minor <= st.budget_minor else " (still over)"
        lines.append(
            f"{i}) {t.title}: saves {money(-t.delta_minor, cur)}, new total "
            f"{money(t.basket.total_minor, cur)}{flag}"
        )
    return "Options: " + "; ".join(lines) + ". Say 'option 1', 'option 2'... to apply one."


def reply_split(total_minor: int, shares: list[int], cur: str, channel: str) -> str:
    if len(set(shares)) == 1:
        each = say_money(shares[0], cur, channel)
        return f"Split {len(shares)} ways, that's {each} each."
    lo, hi = min(shares), max(shares)
    return (
        f"Split {len(shares)} ways: "
        + (
            f"{say_money(hi, cur, channel)} for some and {say_money(lo, cur, channel)} for others"
            if channel == "voice"
            else ", ".join(money(s, cur) for s in shares)
        )
        + f" (adds up to {say_money(total_minor, cur, channel)})."
    )


def _cap(t: str) -> str:
    return t[:1].upper() + t[1:]


def readback(
    basket: Basket,
    address_label: str,
    now: datetime,
    channel: str,
    kind: str = "main",
    extra: str = "",
) -> str:
    cur = basket.currency
    eta = latest_eta(basket)
    when = f", arriving by {speak_time(eta, now)}" if eta else ""
    stores = n_stores(basket)
    if kind == "backup":
        ln = basket.lines[0]
        return _cap(
            f"{ln.offer.title} from {store_label(ln.offer.store_id)} for pickup, "
            f"{say_money(basket.total_minor, cur, channel)}{when}.{extra} Shall I place this backup order?"
        )
    where = f", delivered to {address_label}" if address_label else ""
    return _cap(
        f"{say_money(basket.total_minor, cur, channel)} from {stores} store"
        f"{'s' if stores != 1 else ''}{when}{where}. Shall I place the order?"
    )
