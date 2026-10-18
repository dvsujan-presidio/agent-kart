from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from stores.server import create_app

DATA = Path(__file__).parent / "data"


def client(store: str, **kw) -> TestClient:
    return TestClient(create_app(DATA / f"{store}.json", **kw))


def test_manifest_declares_capabilities():
    m = client("cakecorner").get("/.well-known/ucp").json()
    assert m["ucp"]["version"] == "2026-08-25"
    assert {"catalog.search", "cart", "checkout", "order"} <= set(m["ucp"]["capabilities"])


def test_search_returns_offers_and_terms():
    r = client("snackmart").get("/catalog/search", params={"category": "cups"}).json()
    assert r["terms"]["delivery_fee_minor"] == 3900 and len(r["products"]) == 2
    assert all(p["category"] == "cups" and p["eta"] for p in r["products"])


def test_checkout_total_is_price_plus_fee_and_free_delivery():
    c = client("snackmart")
    small = c.post("/checkout", json={"lines": [{"variant_id": "cups-10-sm", "qty": 1}]}).json()
    assert small["total_minor"] == 7000 + 3900
    big = c.post("/checkout", json={"lines": [{"variant_id": "cola-2l", "qty": 6}]}).json()
    assert big["delivery_fee_minor"] == 0 and big["total_minor"] == 12000 * 6


def test_unknown_variant_conflict():
    assert (
        client("snackmart")
        .post("/cart", json={"lines": [{"variant_id": "nope", "qty": 1}]})
        .status_code
        == 409
    )


def test_order_progresses_and_delay_endpoint():
    c = client("cakecorner", sim_fast=True)
    o = c.post("/checkout", json={"lines": [{"variant_id": "candles-cc", "qty": 1}]}).json()
    assert c.get(f"/orders/{o['order_id']}").json()["status"] == "placed"
    d = c.post(f"/admin/orders/{o['order_id']}/delay", json={"hours": 24}).json()
    assert d["status"] == "delayed" and d["eta"] > o["eta"]


def test_admin_disabled():
    c = client("cakecorner", admin=False)
    o = c.post("/checkout", json={"lines": [{"variant_id": "candles-cc", "qty": 1}]}).json()
    assert c.post(f"/admin/orders/{o['order_id']}/delay").status_code == 403


def test_pickup_store_flagged():
    p = client("nearbybakery").get("/catalog/search").json()["products"]
    assert p and all(x["pickup_only"] for x in p)


@pytest.mark.parametrize("store", ["cakecorner", "snackmart", "partybazaar", "nearbybakery"])
def test_every_store_serves_manifest(store):
    assert client(store).get("/.well-known/ucp").status_code == 200
