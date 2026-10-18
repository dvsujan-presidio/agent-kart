"""Fallback for a delayed order line: in-time replacements (incl. pickup stores)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from contracts.models import Basket, BasketLine, Offer, StoreTerms
from domain.optimizer import DEFAULT_BUFFER, _fee
from domain.quantities import packs_needed


@dataclass(frozen=True)
class FallbackOption:
    replaces: BasketLine
    offer: Offer
    packs: int
    cost_minor: int  # replacement item cost + that store's delivery fee
    extra_minor: int  # cost_minor - the delayed line's total
    new_total_minor: int
    within_budget: bool
    explanation: str


def find_fallback(
    basket: Basket,
    delayed: BasketLine,
    offers: list[Offer],
    terms: dict[str, StoreTerms],
    *,
    deadline: datetime,
    buffer: timedelta = DEFAULT_BUFFER,
    tolerance_minor: int = 0,
) -> FallbackOption | None:
    """Cheapest in-time replacement; None if nothing can arrive in time.

    Prefers options that keep the order within budget (+ tolerance), then lowest cost.
    """
    need_qty = delayed.packs * delayed.offer.pack_size
    unit = delayed.offer.unit
    options: list[FallbackOption] = []
    for o in offers:
        if (
            o.category != delayed.offer.category
            or not o.in_stock
            or o.currency != basket.currency
            or o.store_id == delayed.offer.store_id
        ):
            continue
        if o.eta is None or o.eta > deadline - buffer:
            continue
        packs = packs_needed(need_qty, unit, o.pack_size, o.unit)
        if packs is None:
            continue
        item_cost = o.price_minor * packs
        fee, ok = _fee(item_cost, terms.get(o.store_id))
        if not ok:
            continue
        cost = item_cost + (fee or 0)
        extra = cost - delayed.line_total_minor
        new_total = basket.total_minor + extra
        within = new_total <= basket.budget_minor + tolerance_minor
        explanation = (
            f"{o.store_id} has {o.title} arriving in time, {abs(extra)} minor units "
            f"{'more' if extra >= 0 else 'less'} than the delayed item"
        )
        options.append(
            FallbackOption(delayed, o, packs, cost, extra, new_total, within, explanation)
        )
    if not options:
        return None
    return min(
        options,
        key=lambda f: (not f.within_budget, f.cost_minor, f.offer.store_id, f.offer.variant_id),
    )
