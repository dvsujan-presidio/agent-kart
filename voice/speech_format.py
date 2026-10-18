"""Turn money and times into speakable text. Formatting only; never used to compute."""

from datetime import datetime

_ONES = (
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen"
).split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def _under_100(n: int) -> str:
    if n < 20:
        return _ONES[n]
    t, o = divmod(n, 10)
    return _TENS[t] + (f" {_ONES[o]}" if o else "")


def _under_1000(n: int) -> str:
    h, r = divmod(n, 100)
    parts = []
    if h:
        parts.append(f"{_ONES[h]} hundred")
    if r:
        parts.append(_under_100(r))
    return " ".join(parts)


def number_to_words(n: int) -> str:
    """Indian-style grouping up to crores (lakh/crore), e.g. 125000 -> one lakh twenty five thousand."""
    if n == 0:
        return "zero"
    if n < 0:
        return "minus " + number_to_words(-n)
    parts = []
    for size, name in ((10_000_000, "crore"), (100_000, "lakh"), (1000, "thousand")):
        q, n = divmod(n, size)
        if q:
            parts.append(f"{_under_100(q) if q < 100 else number_to_words(q)} {name}")
    if n:
        parts.append(_under_1000(n))
    return " ".join(parts)


def speak_money(amount_minor: int, currency: str) -> str:
    major, minor = divmod(abs(amount_minor), 100)
    sign = "minus " if amount_minor < 0 else ""
    if currency == "INR":
        s = f"{number_to_words(major)} rupees"
        return sign + (s + f" {number_to_words(minor)} paise" if minor else s)
    s = f"{number_to_words(major)} dollars"
    return sign + (s + f" {number_to_words(minor)} cents" if minor else s)


def speak_time(dt: datetime, now: datetime) -> str:
    hour = dt.hour % 12 or 12
    clock = (
        f"{hour} {'AM' if dt.hour < 12 else 'PM'}"
        if dt.minute == 0
        else f"{hour}:{dt.minute:02d} {'AM' if dt.hour < 12 else 'PM'}"
    )
    days = (dt.date() - now.date()).days
    day = {0: "today", 1: "tomorrow"}.get(days, dt.strftime("%A"))
    return f"{clock} {day}"
