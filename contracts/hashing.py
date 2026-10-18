"""Canonical basket hash used by the approval gate."""

import hashlib
import json

from contracts.models import Basket


def basket_hash(basket: Basket) -> str:
    """sha256 over lines, fees, discounts, total, currency. Excludes `hash` and tradeoffs."""
    payload = {
        "lines": sorted(
            (
                {
                    "store": ln.offer.store_id,
                    "variant": ln.offer.variant_id,
                    "packs": ln.packs,
                    "total": ln.line_total_minor,
                }
                for ln in basket.lines
            ),
            key=lambda d: (d["store"], d["variant"]),
        ),
        "fees": dict(sorted(basket.fees_by_store.items())),
        "discounts": basket.discounts_minor,
        "total": basket.total_minor,
        "currency": basket.currency,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
