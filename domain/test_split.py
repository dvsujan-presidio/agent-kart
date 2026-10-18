from hypothesis import given
from hypothesis import strategies as st

from domain.split import split_equal


def test_rounding():
    assert split_equal(100, 3) == [34, 33, 33]
    assert split_equal(281001, 4) == [70251, 70250, 70250, 70250]


@given(st.integers(0, 10**9), st.integers(1, 50))
def test_sums_exactly_and_fair(total, n):
    s = split_equal(total, n)
    assert sum(s) == total
    assert max(s) - min(s) <= 1


@given(st.integers(0, 10**9), st.lists(st.integers(1, 10), min_size=1, max_size=10))
def test_weighted_sums(total, w):
    assert sum(split_equal(total, len(w), w)) == total
