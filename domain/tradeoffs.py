"""Budget trade-offs: up to N alternatives ranked by quality lost per unit saved."""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from contracts.models import Basket, Currency, ListItem, Offer, StoreTerms, TradeOff
from domain.optimizer import DEFAULT_BUFFER, optimize

# Quality-loss weights: consolidating hurts least, dropping an optional item a bit more,
# shrinking a required item most.
LOSS_CONSOLIDATE = 0.5
LOSS_DROP_OPTIONAL = 1.0
LOSS_DOWNSIZE = 2.0
DOWNSIZE_FACTOR_NUM, DOWNSIZE_FACTOR_DEN = 3, 4


@dataclass
class TradeOffPlan:
    """A TradeOff plus what it changed, so callers can apply it to their session state."""

    tradeoff: TradeOff
    items: list[ListItem]
    dropped: set[str] = field(default_factory=set)
    resized: dict[str, float] = field(default_factory=dict)
    skipped_stores: set[str] = field(default_factory=set)


def _try(items, offers, terms, **kw):
    r = optimize(items, offers, terms, **kw)
    return None if r.missing_required else r.basket


def replace_item(it: ListItem, qty: int) -> ListItem:
    return it.model_copy(
        update={"need_qty": float(qty), "rule": f"{it.rule}; reduced to {qty} {it.unit}"}
    )


def tradeoff_plans(
    items: list[ListItem],
    offers: list[Offer],
    terms: dict[str, StoreTerms],
    *,
    budget_minor: int,
    currency: Currency,
    deadline: datetime,
    buffer: timedelta = DEFAULT_BUFFER,
    exclusions: list[str] | None = None,
    base: Basket | None = None,
    limit: int = 3,
) -> list[TradeOffPlan]:
    kw = dict(
        budget_minor=budget_minor,
        currency=currency,
        deadline=deadline,
        buffer=buffer,
        exclusions=exclusions or [],
    )
    if base is None:
        r = optimize(items, offers, terms, **kw)
        if r.missing_required:
            return []
        base = r.basket
    scored: list[tuple[float, TradeOffPlan]] = []

    def consider(
        title: str,
        basket: Basket | None,
        loss: float,
        new_items: list[ListItem],
        skipped: set[str] | None = None,
    ) -> None:
        if basket is None:
            return
        delta = basket.total_minor - base.total_minor
        if delta >= 0:
            return
        old = {i.category: i for i in items}
        new = {i.category: i for i in new_items}
        plan = TradeOffPlan(
            TradeOff(title=title, delta_minor=delta, basket=basket),
            new_items,
            dropped=set(old) - set(new),
            resized={c: new[c].need_qty for c in new if new[c].need_qty != old[c].need_qty},
            skipped_stores=skipped or set(),
        )
        scored.append((loss / -delta, plan))

    def label(c: str) -> str:
        return c.replace("_", " ")

    optional = [i for i, it in enumerate(items) if not it.required]
    # 1. drop one or two optional items
    for n in (1, 2):
        for combo in itertools.combinations(optional, n):
            rest = [it for i, it in enumerate(items) if i not in combo]
            title = "Drop " + " + ".join(label(items[i].category) for i in combo)
            consider(title, _try(rest, offers, terms, **kw), LOSS_DROP_OPTIONAL * n, rest)

    # 2. downsize each item to 75% of the planned quantity
    for i, it in enumerate(items):
        smaller = math.ceil(it.need_qty * DOWNSIZE_FACTOR_NUM / DOWNSIZE_FACTOR_DEN)
        if smaller >= it.need_qty or smaller < 1:
            continue
        new_items = items[:i] + [replace_item(it, smaller)] + items[i + 1 :]
        consider(
            f"Reduce {label(it.category)} to {smaller} {it.unit}",
            _try(new_items, offers, terms, **kw),
            LOSS_DOWNSIZE,
            new_items,
        )

    # 3. consolidate: stop using one of the stores
    stores = {ln.offer.store_id for ln in base.lines}
    if len(stores) > 1:
        for s in sorted(stores):
            consider(
                f"Skip {s}, buy from the other stores",
                _try(items, [o for o in offers if o.store_id != s], terms, **kw),
                LOSS_CONSOLIDATE,
                items,
                {s},
            )

    seen = {base.hash}
    ranked: list[TradeOffPlan] = []
    # within-budget options first, then least quality lost per unit saved
    order = sorted(
        scored,
        key=lambda x: (
            x[1].tradeoff.basket.total_minor > budget_minor,
            x[0],
            x[1].tradeoff.basket.total_minor,
            x[1].tradeoff.title,
        ),
    )
    for _, plan in order:
        h = plan.tradeoff.basket.hash
        if h not in seen:
            seen.add(h)
            ranked.append(plan)
        if len(ranked) == limit:
            break
    return ranked


def tradeoffs(items, offers, terms, **kw) -> list[TradeOff]:
    return [p.tradeoff for p in tradeoff_plans(items, offers, terms, **kw)]
