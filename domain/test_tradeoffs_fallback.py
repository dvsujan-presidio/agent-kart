from datetime import UTC, datetime, timedelta

from contracts.models import ListItem, Offer, StoreTerms
from domain.fallback import find_fallback
from domain.optimizer import optimize
from domain.tradeoffs import tradeoffs

DEADLINE = datetime(2026, 10, 18, 18, tzinfo=UTC)


def offer(store, cat, price, pack=1.0, unit="pcs", eta_h=-10, vid=None):
    return Offer(
        store_id=store,
        source="ucp_mock",
        product_id=cat,
        variant_id=vid or f"{store}-{cat}",
        title=f"{store} {cat}",
        category=cat,
        pack_size=pack,
        unit=unit,
        price_minor=price,
        currency="INR",
        eta=DEADLINE + timedelta(hours=eta_h),
    )


def item(cat, qty=1, unit="pcs", required=True):
    return ListItem(category=cat, need_qty=qty, unit=unit, rule="r", required=required)


ITEMS = [
    item("cake", 1500, "g"),
    item("cups", 20),
    item("hats", 10, required=False),
    item("balloons", 20, required=False),
]
OFFERS = [
    offer("a", "cake", 100000, 1500, "g"),
    offer("a", "cake", 70000, 1000, "g", vid="a-cake-1kg"),
    offer("a", "cups", 6000, 10),
    offer("b", "cups", 5000, 10),
    offer("b", "hats", 8000, 10),
    offer("b", "balloons", 4000, 10),
]
TERMS = {
    "a": StoreTerms(store_id="a", delivery_fee_minor=4900),
    "b": StoreTerms(store_id="b", delivery_fee_minor=5900),
}
KW = dict(currency="INR", deadline=DEADLINE)


def test_tradeoffs_over_budget_ranked_and_limited():
    base = optimize(ITEMS, OFFERS, TERMS, budget_minor=200000, **KW).basket
    ts = tradeoffs(ITEMS, OFFERS, TERMS, budget_minor=200000, **KW)
    assert 1 <= len(ts) <= 3
    assert all(t.delta_minor < 0 for t in ts)
    assert all(t.basket.total_minor == base.total_minor + t.delta_minor for t in ts)
    assert len({t.basket.hash for t in ts}) == len(ts)
    assert base.hash not in {t.basket.hash for t in ts}


def test_tradeoffs_prefers_within_budget_options():
    base = optimize(ITEMS, OFFERS, TERMS, budget_minor=1, **KW).basket
    budget = base.total_minor - 5000
    ts = tradeoffs(ITEMS, OFFERS, TERMS, budget_minor=budget, **KW)
    within = [t.basket.total_minor <= budget for t in ts]
    assert within == sorted(within, reverse=True)  # all True first
    assert within[0]


def test_no_tradeoffs_when_nothing_cheaper():
    assert (
        tradeoffs([item("cups", 10)], [offer("a", "cups", 100, 10)], {}, budget_minor=10**6, **KW)
        == []
    )


def test_fallback_picks_in_time_replacement_within_budget():
    items = [item("cake", 1000, "g")]
    delayed_offer = offer("cakecorner", "cake", 90000, 1000, "g")
    pickup = offer("nearby", "cake", 102000, 1000, "g", eta_h=-6)
    too_late = offer("far", "cake", 50000, 1000, "g", eta_h=2)
    cheap_too_early_ok = offer("other", "cake", 120000, 1000, "g", eta_h=-5)
    terms = {
        "cakecorner": StoreTerms(store_id="cakecorner", delivery_fee_minor=0),
        "nearby": StoreTerms(store_id="nearby", delivery_fee_minor=0),
    }
    base = optimize(items, [delayed_offer], terms, budget_minor=300000, **KW).basket
    fb = find_fallback(
        base,
        base.lines[0],
        [delayed_offer, pickup, too_late, cheap_too_early_ok],
        terms,
        deadline=DEADLINE,
    )
    assert fb.offer.store_id == "nearby" and fb.extra_minor == 12000 and fb.within_budget


def test_fallback_none_when_nothing_in_time():
    items = [item("cake", 1000, "g")]
    o = offer("a", "cake", 100, 1000, "g")
    base = optimize(items, [o], {}, budget_minor=10**6, **KW).basket
    assert (
        find_fallback(
            base,
            base.lines[0],
            [o, offer("b", "cake", 1, 1000, "g", eta_h=5)],
            {},
            deadline=DEADLINE,
        )
        is None
    )
