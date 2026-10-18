from datetime import UTC, datetime

from contracts.hashing import basket_hash
from contracts.models import Basket, BasketLine, Offer


def _offer(variant="v1"):
    return Offer(
        store_id="s",
        source="ucp_mock",
        product_id="p",
        variant_id=variant,
        title="t",
        category="cups",
        pack_size=10,
        unit="pcs",
        price_minor=4000,
        currency="INR",
        eta=datetime(2026, 10, 18, tzinfo=UTC),
    )


def _basket(packs=1):
    line = BasketLine(offer=_offer(), packs=packs, line_total_minor=4000 * packs)
    return Basket(
        lines=[line],
        fees_by_store={"s": 4900},
        total_minor=4000 * packs + 4900,
        budget_minor=300000,
        currency="INR",
        hash="",
    )


def test_hash_stable_and_changes_with_content():
    assert basket_hash(_basket()) == basket_hash(_basket())
    assert basket_hash(_basket(1)) != basket_hash(_basket(2))
