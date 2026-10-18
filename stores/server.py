"""Mock UCP-style merchant server. One codebase, configured by STORE_ID / DATA_FILE / PORT.

Implements the UCP discovery shape (/.well-known/ucp with capabilities) plus a small REST
binding for catalog search, cart, checkout, orders and a flag-guarded delay endpoint. This is a
simplified subset of UCP for the hackathon demo, not a conformance-tested implementation.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

TZ = ZoneInfo("Asia/Kolkata")
UCP_VERSION = "2026-08-25"
# seconds of real time per simulated stage when SIM_FAST=1 (demo mode)
STAGES = ["placed", "packed", "out_for_delivery", "delivered"]


def _eta(rule: dict, now: datetime) -> datetime:
    if "hours" in rule:
        return now + timedelta(hours=rule["hours"])
    h, m = map(int, rule["time"].split(":"))
    return (now + timedelta(days=rule["days"])).replace(hour=h, minute=m, second=0, microsecond=0)


class Line(BaseModel):
    variant_id: str
    qty: int = 1


class CartRequest(BaseModel):
    lines: list[Line]


class CheckoutRequest(BaseModel):
    lines: list[Line]
    address: dict | None = None
    approval_ref: str | None = None  # opaque reference from the agent, stored for audit only


class DelayRequest(BaseModel):
    hours: float = 24


def create_app(
    store_file: str | Path,
    *,
    base_url: str = "",
    admin: bool | None = None,
    sim_fast: bool | None = None,
) -> FastAPI:
    cfg = json.loads(Path(store_file).read_text())
    admin = os.getenv("STORE_ADMIN", "true") == "true" if admin is None else admin
    sim_fast = os.getenv("SIM_FAST", "true") == "true" if sim_fast is None else sim_fast
    products = {p["variant_id"]: p for p in cfg["products"]}
    orders: dict[str, dict] = {}
    app = FastAPI(title=f"{cfg['name']} (mock UCP merchant)")

    def now() -> datetime:
        return datetime.now(TZ)

    def terms() -> dict:
        return {
            "store_id": cfg["id"],
            "delivery_fee_minor": cfg["delivery_fee"] * 100,
            "free_delivery_above_minor": (cfg["free_above"] * 100) or None,
            "min_order_minor": (cfg["min_order"] * 100) or None,
        }

    def view(p: dict) -> dict:
        return {
            k: p[k]
            for k in (
                "product_id",
                "variant_id",
                "title",
                "category",
                "pack_size",
                "unit",
                "price_minor",
                "rating",
                "in_stock",
                "attributes",
            )
        } | {
            "currency": cfg.get("currency", "INR"),
            "eta": _eta(p["eta_rule"], now()).isoformat(),
            "pickup_only": cfg.get("pickup_only", False),
        }

    def price(lines: list[Line]) -> dict:
        sub = 0
        out = []
        for ln in lines:
            p = products.get(ln.variant_id)
            if p is None or not p["in_stock"]:
                raise HTTPException(409, f"unavailable: {ln.variant_id}")
            total = p["price_minor"] * ln.qty
            sub += total
            out.append({"variant_id": ln.variant_id, "qty": ln.qty, "line_total_minor": total})
        t = terms()
        fee = t["delivery_fee_minor"]
        if t["free_delivery_above_minor"] and sub >= t["free_delivery_above_minor"]:
            fee = 0
        return {
            "lines": out,
            "subtotal_minor": sub,
            "delivery_fee_minor": fee,
            "total_minor": sub + fee,
            "currency": "INR",
        }

    @app.get("/.well-known/ucp")
    def manifest() -> dict:
        return {
            "ucp": {
                "version": UCP_VERSION,
                "services": {
                    "dev.ucp.shopping": {
                        "version": UCP_VERSION,
                        "transport": "rest",
                        "endpoint": base_url or "/",
                    }
                },
                "capabilities": [
                    "catalog.search",
                    "catalog.lookup",
                    "cart",
                    "checkout",
                    "discount",
                    "fulfillment",
                    "order",
                    "permalink",
                ],
            },
            "store": {
                "id": cfg["id"],
                "name": cfg["name"],
                "currency": "INR",
                "timezone": "Asia/Kolkata",
                "pickup_only": cfg.get("pickup_only", False),
            },
        }

    @app.get("/catalog/search")
    def search(q: str | None = None, category: str | None = None) -> dict:
        items = [
            view(p)
            for p in products.values()
            if (not category or p["category"] == category)
            and (not q or q.lower() in p["title"].lower())
        ]
        return {"store_id": cfg["id"], "terms": terms(), "products": items}

    @app.get("/catalog/lookup/{variant_id}")
    def lookup(variant_id: str) -> dict:
        if variant_id not in products:
            raise HTTPException(404, "unknown variant")
        return view(products[variant_id])

    @app.post("/cart")
    def cart(req: CartRequest) -> dict:
        return {"cart_id": uuid.uuid4().hex[:12], **price(req.lines)}

    @app.post("/checkout")
    def checkout(req: CheckoutRequest) -> dict:
        priced = price(req.lines)
        eta = max(_eta(products[ln.variant_id]["eta_rule"], now()) for ln in req.lines)
        oid = f"{cfg['id'][:3].upper()}-{uuid.uuid4().hex[:8]}"
        orders[oid] = {
            "order_id": oid,
            "store_id": cfg["id"],
            "created": time.time(),
            "eta": eta,
            "delayed": False,
            "approval_ref": req.approval_ref,
            "address": req.address,
            **priced,
        }
        return order_view(orders[oid])

    def stage(o: dict) -> str:
        if o["delayed"]:
            return "delayed"
        step = 8 if sim_fast else 1800  # seconds per stage
        return STAGES[min(int((time.time() - o["created"]) // step), len(STAGES) - 1)]

    def order_view(o: dict) -> dict:
        return {
            "order_id": o["order_id"],
            "store_id": o["store_id"],
            "status": stage(o),
            "eta": o["eta"].isoformat(),
            "total_minor": o["total_minor"],
            "delivery_fee_minor": o["delivery_fee_minor"],
            "lines": o["lines"],
        }

    @app.get("/orders/{order_id}")
    def get_order(order_id: str) -> dict:
        if order_id not in orders:
            raise HTTPException(404, "unknown order")
        return order_view(orders[order_id])

    @app.post("/admin/orders/{order_id}/delay")
    def delay(order_id: str, req: DelayRequest | None = None) -> dict:
        if not admin:
            raise HTTPException(403, "admin disabled")
        if order_id not in orders:
            raise HTTPException(404, "unknown order")
        o = orders[order_id]
        o["delayed"] = True
        o["eta"] = o["eta"] + timedelta(hours=(req.hours if req else 24))
        return order_view(o)

    @app.post("/admin/reset")
    def reset() -> dict:
        if not admin:
            raise HTTPException(403, "admin disabled")
        orders.clear()
        return {"ok": True}

    @app.get("/admin/orders")
    def list_orders() -> list[dict]:
        return [order_view(o) for o in orders.values()]

    return app


def app_from_env() -> FastAPI:  # uvicorn --factory stores.server:app_from_env
    data = Path(
        os.environ.get("DATA_FILE")
        or Path(__file__).parent / "data" / f"{os.environ['STORE_ID']}.json"
    )
    return create_app(data, base_url=os.getenv("PUBLIC_URL", ""))
