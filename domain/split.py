"""Group split in integer minor units. Shares always sum exactly to the total."""


def split_equal(total_minor: int, payers: int, weights: list[int] | None = None) -> list[int]:
    if payers < 1:
        raise ValueError("payers must be >= 1")
    if total_minor < 0:
        raise ValueError("total must be >= 0")
    w = weights or [1] * payers
    if len(w) != payers or any(x <= 0 for x in w):
        raise ValueError("weights must be positive and match payers")
    tw = sum(w)
    shares = [total_minor * x // tw for x in w]
    rem = total_minor - sum(shares)
    # distribute remainder one minor unit at a time, largest fractional part first, stable
    order = sorted(range(payers), key=lambda i: (-(total_minor * w[i] % tw), i))
    for i in order[:rem]:
        shares[i] += 1
    return shares
