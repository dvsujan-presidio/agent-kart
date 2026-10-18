import pytest

from domain.quantities import list_scenarios, packs_needed, plan_list


def by_cat(items):
    return {i.category: i for i in items}


def test_all_templates_load_and_make_sane_lists():
    assert set(list_scenarios()) == {
        "birthday_party",
        "camping_weekend",
        "first_apartment",
        "home_gym",
    }
    for s in list_scenarios():
        items = plan_list(s, 4, preferences={"beds": 2})
        assert items and all(i.need_qty > 0 for i in items)


def test_birthday_rules():
    d = by_cat(plan_list("birthday_party", 10))
    assert d["drinks"].need_qty == 6000 and d["drinks"].rule == "10 guests x 600 ml = 6000 ml"
    assert d["cups"].need_qty == 15
    assert d["cake"].need_qty == 1000


def test_cake_minimum_applies_for_tiny_party():
    d = by_cat(plan_list("birthday_party", 2))
    assert d["cake"].need_qty == 500 and "minimum" in d["cake"].rule


def test_exclusions_by_category_and_alias():
    d = by_cat(plan_list("birthday_party", 10, exclusions=["Plates", "hats"]))
    assert "plates" not in d and "party_hats" not in d


def test_per_pref():
    d = by_cat(plan_list("first_apartment", 2, preferences={"beds": 3}))
    assert d["sheets"].need_qty == 6


def test_bad_inputs():
    with pytest.raises(KeyError):
        plan_list("nope", 3)
    with pytest.raises(ValueError):
        plan_list("birthday_party", 0)


@pytest.mark.parametrize(
    "need,nu,pack,pu,expect",
    [
        (6000, "ml", 2, "L", 3),
        (15, "pcs", 10, "pcs", 2),
        (15, "pcs", 25, "pcs", 1),
        (1000, "g", 1, "kg", 1),
        (1000, "g", 1.5, "kg", 1),
        (1000, "g", 0.5, "kg", 2),
        (1000, "g", 1, "pcs", None),
    ],
)
def test_packs_needed(need, nu, pack, pu, expect):
    assert packs_needed(need, nu, pack, pu) == expect
