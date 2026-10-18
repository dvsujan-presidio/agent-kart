"""Exact basket optimizer: cheapest total landed cost (items + delivery - discounts).

Pure and deterministic. Depth-first search over (offer, packs) choices per list item with
branch-and-bound; fees depend on per-store subtotals (free-delivery thresholds, minimum
orders), so we search assignments instead of assuming cheapest-per-item is optimal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from contracts.hashing import basket_hash
from contracts.models import (
    Basket,
    BasketLine,
    Currency,
    Exclusion,
    ListItem,
    Offer,
    StoreTerms,
)
from domain.quantities import packs_needed

DEFAULT_BUFFER = timedelta(hours=2)


@dataclass(frozen=True)
class Choice:
    item_idx: int
    offer: Offer
    packs: int
    gross: int  # price * packs
    discount: int  # per-pack discount * packs

    @property
    def net(self) -> int:
        return self.gross - self.discount


@dataclass
class OptimizeResult:
    basket: Basket
    missing_required: list[str] = field(default_factory=list)
    skipped_optional: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FeeInsight:
    optimal_total_minor: int
    naive_total_minor: int
    saving_minor: int
    optimal_stores: int
    naive_stores: int


def _discount(offer: Offer, packs: int) -> int:
    return (
        min(offer.discount.amount_minor * packs, offer.price_minor * packs) if offer.discount else 0
    )


def screen_offers(
    items: list[ListItem],
    offers: list[Offer],
    *,
    currency: Currency,
    deadline: datetime,
    buffer: timedelta,
    exclusions: list[str],
) -> tuple[list[Offer], list[Exclusion]]:
    """Split offers into usable and excluded (with reason)."""
    cats = {i.category for i in items}
    ex = {e.strip().lower() for e in exclusions}
    ok: list[Offer] = []
    out: list[Exclusion] = []
    for o in offers:
        if o.category not in cats:
            continue
        if o.currency != currency:
            continue  # never mix currencies
        if o.category in ex:
            out.append(Exclusion(offer=o, reason="user_excluded"))
        elif not o.in_stock:
            out.append(Exclusion(offer=o, reason="out_of_stock"))
        elif o.eta is not None and o.eta > deadline - buffer:
            out.append(Exclusion(offer=o, reason="late"))
        else:
            ok.append(o)
    return ok, out


def _candidates(items: list[ListItem], offers: list[Offer]) -> list[list[Choice]]:
    cands: list[list[Choice]] = []
    for idx, item in enumerate(items):
        row: list[Choice] = []
        for o in offers:
            if o.category != item.category:
                continue
            packs = packs_needed(item.need_qty, item.unit, o.pack_size, o.unit)
            if packs is None:
                continue
            row.append(Choice(idx, o, packs, o.price_minor * packs, _discount(o, packs)))
        row.sort(key=lambda c: (c.net, c.offer.store_id, c.offer.variant_id))
        cands.append(row)
    return cands


def _fee(subtotal: int, t: StoreTerms | None) -> tuple[int | None, bool]:
    """(fee or None if unknown, order_ok)."""
    if t is None:
        return None, True
    if t.min_order_minor is not None and subtotal < t.min_order_minor:
        return 0, False
    if t.free_delivery_above_minor is not None and subtotal >= t.free_delivery_above_minor:
        return 0, True
    return t.delivery_fee_minor, True


def evaluate(
    choices: list[Choice], terms: dict[str, StoreTerms]
) -> tuple[int, dict[str, int | None], int, bool]:
    """(total, fees_by_store, discounts, valid). Unknown fees count as 0 and are reported as None."""
    subtotals: dict[str, int] = {}
    for c in choices:
        subtotals[c.offer.store_id] = subtotals.get(c.offer.store_id, 0) + c.gross
    fees: dict[str, int | None] = {}
    valid = True
    for store, sub in subtotals.items():
        fee, ok = _fee(sub, terms.get(store))
        fees[store] = fee
        valid = valid and ok
    discounts = sum(c.discount for c in choices)
    total = sum(subtotals.values()) - discounts + sum(f or 0 for f in fees.values())
    return total, fees, discounts, valid


def _rank(choices: list[Choice], total: int) -> tuple:
    rating = sum(c.offer.rating or 0 for c in choices)
    stores = len({c.offer.store_id for c in choices})
    ident = tuple(sorted((c.offer.store_id, c.offer.variant_id, c.packs) for c in choices))
    return (total, -rating, stores, ident)


def _search(cands: list[list[Choice]], terms: dict[str, StoreTerms]) -> list[Choice] | None:
    order = sorted(range(len(cands)), key=lambda i: len(cands[i]))  # fail-first
    best: tuple | None = None
    best_choices: list[Choice] | None = None
    picked: list[Choice] = []

    def dfs(k: int, partial_net: int) -> None:
        nonlocal best, best_choices
        if best is not None and partial_net > best[0]:
            return  # fees >= 0 and nets >= 0, so the total can only grow
        if k == len(order):
            total, _, _, valid = evaluate(picked, terms)
            if not valid:
                return
            key = _rank(picked, total)
            if best is None or key < best:
                best, best_choices = key, list(picked)
            return
        for c in cands[order[k]]:
            picked.append(c)
            dfs(k + 1, partial_net + c.net)
            picked.pop()

    dfs(0, 0)
    return best_choices


def _build_basket(
    choices: list[Choice],
    terms: dict[str, StoreTerms],
    *,
    budget_minor: int,
    currency: Currency,
    excluded: list[Exclusion],
    feasible_extra: bool,
) -> Basket:
    total, fees, discounts, _ = evaluate(choices, terms)
    lines = [
        BasketLine(offer=c.offer, packs=c.packs, line_total_minor=c.gross)
        for c in sorted(choices, key=lambda c: c.item_idx)
    ]
    basket = Basket(
        lines=lines,
        fees_by_store=fees,
        discounts_minor=discounts,
        total_minor=total,
        total_is_estimate=any(f is None for f in fees.values()),
        budget_minor=budget_minor,
        currency=currency,
        excluded=excluded,
        feasible=feasible_extra and total <= budget_minor,
        hash="",
    )
    return basket.model_copy(update={"hash": basket_hash(basket)})


def optimize(
    items: list[ListItem],
    offers: list[Offer],
    terms: dict[str, StoreTerms],
    *,
    budget_minor: int,
    currency: Currency,
    deadline: datetime,
    buffer: timedelta = DEFAULT_BUFFER,
    exclusions: list[str] | None = None,
) -> OptimizeResult:
    usable, excluded = screen_offers(
        items,
        offers,
        currency=currency,
        deadline=deadline,
        buffer=buffer,
        exclusions=exclusions or [],
    )
    cands = _candidates(items, usable)
    missing = [items[i].category for i, row in enumerate(cands) if not row and items[i].required]
    skipped = [
        items[i].category for i, row in enumerate(cands) if not row and not items[i].required
    ]
    live = [(i, row) for i, row in enumerate(cands) if row]
    sub_items = [items[i] for i, _ in live]
    sub_cands = [
        [Choice(n, c.offer, c.packs, c.gross, c.discount) for c in row]
        for n, (_, row) in enumerate(live)
    ]
    best = _search(sub_cands, terms) if sub_cands else []
    if best is None:  # every assignment violates a minimum order
        best = []
        missing = missing + [i.category for i in sub_items if i.required]
    basket = _build_basket(
        best,
        terms,
        budget_minor=budget_minor,
        currency=currency,
        excluded=excluded,
        feasible_extra=not missing,
    )
    return OptimizeResult(basket=basket, missing_required=missing, skipped_optional=skipped)


def fee_insight(
    items: list[ListItem],
    offers: list[Offer],
    terms: dict[str, StoreTerms],
    *,
    currency: Currency,
    deadline: datetime,
    buffer: timedelta = DEFAULT_BUFFER,
    exclusions: list[str] | None = None,
) -> FeeInsight | None:
    """Optimal total vs the naive 'cheapest per item, ignore delivery' total."""
    usable, _ = screen_offers(
        items,
        offers,
        currency=currency,
        deadline=deadline,
        buffer=buffer,
        exclusions=exclusions or [],
    )
    cands = [row for row in _candidates(items, usable) if row]
    if not cands:
        return None
    best = _search(cands, terms)
    if best is None:
        return None
    naive = [row[0] for row in cands]
    t_opt, *_ = evaluate(best, terms)
    t_naive, *_ = evaluate(naive, terms)
    return FeeInsight(
        t_opt,
        t_naive,
        t_naive - t_opt,
        len({c.offer.store_id for c in best}),
        len({c.offer.store_id for c in naive}),
    )
