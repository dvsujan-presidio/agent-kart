import itertools
import random
from datetime import UTC, datetime, timedelta

from contracts.hashing import basket_hash
from contracts.models import Discount, ListItem, Offer, StoreTerms
from domain.optimizer import Choice, _candidates, evaluate, fee_insight, optimize

DEADLINE = datetime(2026, 10, 18, 18, tzinfo=UTC)


def offer(store, cat, price, *, pack=1.0, unit="pcs", eta_h=-10, stock=True, rating=None, vid=None):
    return Offer(
        store_id=store,
        source="ucp_mock",
        product_id=f"{store}-{cat}",
        variant_id=vid or f"{store}-{cat}-{pack}",
        title=cat,
        category=cat,
        pack_size=pack,
        unit=unit,
        price_minor=price,
        currency="INR",
        rating=rating,
        eta=DEADLINE + timedelta(hours=eta_h) if eta_h is not None else None,
        in_stock=stock,
    )


def item(cat, qty=1, unit="pcs", required=True):
    return ListItem(category=cat, need_qty=qty, unit=unit, rule="r", required=required)


def run(items, offers, terms, budget=10**9, **kw):
    return optimize(
        items, offers, terms, budget_minor=budget, currency="INR", deadline=DEADLINE, **kw
    )


def test_consolidation_beats_naive_cheapest():
    # b is 1000 cheaper for cups but adds a 5900 fee; consolidating at a is best.
    items = [item("cake"), item("cups")]
    offers = [offer("a", "cake", 50000), offer("a", "cups", 5000), offer("b", "cups", 4000)]
    terms = {
        "a": StoreTerms(store_id="a", delivery_fee_minor=4900),
        "b": StoreTerms(store_id="b", delivery_fee_minor=5900),
    }
    r = run(items, offers, terms)
    assert {ln.offer.store_id for ln in r.basket.lines} == {"a"}
    assert r.basket.total_minor == 50000 + 5000 + 4900
    ins = fee_insight(items, offers, terms, currency="INR", deadline=DEADLINE)
    assert ins.saving_minor == 5900 + 4900 + 50000 + 4000 - r.basket.total_minor > 0
    assert ins.naive_stores == 2 and ins.optimal_stores == 1


def test_spending_more_to_reach_free_delivery_wins():
    items = [item("a1"), item("a2")]
    offers = [
        offer("s", "a1", 60000),
        offer("s", "a2", 30000, vid="cheap"),
        offer("s", "a2", 35000, vid="pricey"),
    ]
    terms = {
        "s": StoreTerms(store_id="s", delivery_fee_minor=9900, free_delivery_above_minor=95000)
    }
    r = run(items, offers, terms)
    assert [ln.offer.variant_id for ln in r.basket.lines][1] == "pricey"
    assert r.basket.total_minor == 95000 and r.basket.fees_by_store == {"s": 0}


def test_late_and_stock_and_user_exclusions():
    items = [item("cups"), item("plates", required=False)]
    offers = [
        offer("a", "cups", 5000),
        offer("p", "cups", 1000, eta_h=24),
        offer("a", "plates", 100, stock=False),
        offer("b", "plates", 200),
    ]
    r = run(items, offers, {}, exclusions=["plates"])
    reasons = {(e.offer.store_id, e.offer.category): e.reason for e in r.basket.excluded}
    assert reasons[("p", "cups")] == "late"
    assert reasons[("a", "plates")] == "user_excluded"  # exclusion wins over stock
    assert [ln.offer.category for ln in r.basket.lines] == ["cups"]
    assert r.skipped_optional == ["plates"]


def test_buffer_makes_near_deadline_offer_late():
    r = run([item("cake")], [offer("a", "cake", 100, eta_h=-1)], {})
    assert r.missing_required == ["cake"] and not r.basket.feasible


def test_unknown_eta_allowed_and_unknown_fee_flags_estimate():
    r = run([item("cup")], [offer("x", "cup", 500, eta_h=None)], {})
    assert r.basket.total_is_estimate and r.basket.fees_by_store == {"x": None}


def test_over_budget_still_returns_cheapest_but_infeasible():
    r = run([item("cake")], [offer("a", "cake", 90000)], {}, budget=50000)
    assert r.basket.total_minor == 90000 and not r.basket.feasible and not r.missing_required


def test_min_order_enforced():
    items = [item("x")]
    offers = [offer("a", "x", 1000), offer("b", "x", 5000)]
    terms = {
        "a": StoreTerms(store_id="a", min_order_minor=3000),
        "b": StoreTerms(store_id="b", delivery_fee_minor=0),
    }
    assert run(items, offers, terms).basket.lines[0].offer.store_id == "b"


def test_pack_rounding_and_mixed_currency_ignored():
    items = [item("drinks", 6000, "ml")]
    usd = offer("u", "drinks", 1, pack=2, unit="L").model_copy(update={"currency": "USD"})
    r = run(items, [offer("a", "drinks", 9000, pack=2, unit="L"), usd], {})
    assert r.basket.lines[0].packs == 3 and r.basket.total_minor == 27000


def test_tie_break_rating_then_fewer_stores():
    r = run([item("x")], [offer("a", "x", 100, rating=3.0), offer("b", "x", 100, rating=4.5)], {})
    assert r.basket.lines[0].offer.store_id == "b"


def test_hash_matches_contract_and_is_stable():
    r = run([item("x")], [offer("a", "x", 100)], {})
    assert r.basket.hash == basket_hash(r.basket)


def _brute(items, offers, terms):
    cands = [row for row in _candidates(items, offers) if row]
    best = None
    for combo in itertools.product(*cands):
        total, _, _, valid = evaluate(list(combo), terms)
        if valid and (best is None or total < best):
            best = total
    return best


def test_matches_brute_force_on_random_cases():
    rng = random.Random(7)
    for _ in range(300):
        stores = ["a", "b", "c"][: rng.randint(1, 3)]
        cats = [f"c{i}" for i in range(rng.randint(1, 5))]
        items = [item(c, qty=rng.randint(1, 5)) for c in cats]
        offers = [
            offer(s, c, rng.randint(100, 3000), pack=rng.choice([1, 2, 5]), vid=f"{s}{c}{k}")
            for s in stores
            for c in cats
            for k in range(rng.randint(0, 2))
        ]
        terms = {
            s: StoreTerms(
                store_id=s,
                delivery_fee_minor=rng.choice([0, 500, 2000]),
                free_delivery_above_minor=rng.choice([None, 3000, 8000]),
                min_order_minor=rng.choice([None, None, 500]),
            )
            for s in stores
        }
        want = _brute(items, offers, terms)
        got = run(items, offers, terms)
        if want is None or got.missing_required:
            continue
        assert got.basket.total_minor == want
        # invariants
        assert (
            sum(ln.line_total_minor for ln in got.basket.lines)
            - got.basket.discounts_minor
            + sum(f or 0 for f in got.basket.fees_by_store.values())
            == got.basket.total_minor
        )


def test_choice_net_never_negative():
    o = offer("a", "x", 100).model_copy(update={"discount": Discount(code="C", amount_minor=500)})
    assert run([item("x")], [o], {}).basket.total_minor == 0
    assert Choice(0, o, 1, 100, 100).net == 0
