import pytest

from voice.confirmation import is_confirmed

YES = [
    "yes",
    "Yes.",
    "yes please",
    "yeah",
    "confirm",
    "place the order",
    "go ahead",
    "haan",
    "haan karo",
    "theek hai",
    "okay",
    "ok go ahead",
    "yes plz",
    "s",
    "yaa",
    "yes, place the order",
    "sure",
    "yes confirm",
    "proceed",
    "sounds good yes",
    "yes do it",
]
NO = [
    "",
    "   ",
    "no",
    "nope",
    "wait",
    "wait actually",
    "yes but change the cake",
    "yes however",
    "hold on",
    "don't",
    "do not place it",
    "nahi",
    "ruko",
    "no thanks",
    "yes and add candles",
    "what is the total",
    "yes 3000",
    "maybe",
    "hmm",
    "cancel",
    "stop",
    "not yet",
    "I don't know",
    "can you repeat that",
    "change the cake",
    "make it cheaper",
    "ok but remove hats",
]


@pytest.mark.parametrize("u", YES)
def test_accepts(u):
    assert is_confirmed(u)


@pytest.mark.parametrize("u", NO)
def test_rejects(u):
    assert not is_confirmed(u)


def test_none_and_low_confidence():
    assert not is_confirmed(None)
    assert not is_confirmed("yes", confidence=0.2)
    assert is_confirmed("yes", confidence=0.9)


def test_too_long_rejected():
    assert not is_confirmed("yes " * 11)
