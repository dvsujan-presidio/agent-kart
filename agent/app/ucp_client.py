"""Shared UCP-style client: discovery -> catalog search -> checkout -> order status.

Reads the service endpoint and capabilities from the store's /.well-known/ucp manifest and only
calls capabilities the manifest declares. Store text is untrusted and sanitized before use.
"""

from __future__ import annotations

import re
from datetime import datetime

import httpx

from contracts.models import Offer, StoreTerms

_CTRL = re.compile(r"[\x00-\x1f\x7f<>`]")


def clean_text(s: str, limit: int = 120) -> str:
    """Store data is untrusted: strip control chars and markup, cap length."""
    return _CTRL.sub(" ", str(s)).strip()[:limit]


class StoreClient:
    def __init__(self, base_url: str, http: httpx.AsyncClient):
        self.base_url = base_url.rstrip("/")
        self.http = http
        self.manifest: dict | None = None

    @property
    def _endpoint(self) -> str:
        svc = (self.manifest or {}).get("ucp", {}).get("services", {}).get("dev.ucp.shopping", {})
        ep = svc.get("endpoint", "")
        return ep.rstrip("/") if ep.startswith("http") else self.base_url

    def supports(self, capability: str) -> bool:
        return capability in ((self.manifest or {}).get("ucp", {}).get("capabilities", []))

    async def discover(self) -> dict:
        r = await self.http.get(f"{self.base_url}/.well-known/ucp")
        r.raise_for_status()
        self.manifest = r.json()
        return self.manifest

    @property
    def store_id(self) -> str:
        return (self.manifest or {}).get("store", {}).get("id", self.base_url)

    async def search(self, category: str | None = None) -> tuple[StoreTerms, list[Offer]]:
        if self.manifest is None:
            await self.discover()
        if not self.supports("catalog.search"):
            raise RuntimeError(f"{self.base_url} does not declare catalog.search")
        r = await self.http.get(
            f"{self._endpoint}/catalog/search", params={"category": category} if category else None
        )
        r.raise_for_status()
        data = r.json()
        terms = StoreTerms(**data["terms"])
        offers = [
            Offer(
                store_id=data["store_id"],
                source="ucp_mock",
                product_id=p["product_id"],
                variant_id=p["variant_id"],
                title=clean_text(p["title"]),
                category=p["category"],
                pack_size=p["pack_size"],
                unit=p["unit"],
                price_minor=p["price_minor"],
                currency=p["currency"],
                rating=p.get("rating"),
                eta=datetime.fromisoformat(p["eta"]) if p.get("eta") else None,
                in_stock=p["in_stock"],
                attributes=p.get("attributes", {}),
                pickup_only=p.get("pickup_only", False),
            )
            for p in data["products"]
        ]
        return terms, offers

    async def cart(self, lines: list[dict]) -> dict:
        r = await self.http.post(f"{self._endpoint}/cart", json={"lines": lines})
        r.raise_for_status()
        return r.json()

    async def checkout(self, lines: list[dict], address: dict | None, approval_ref: str) -> dict:
        if not self.supports("checkout"):
            raise RuntimeError(f"{self.store_id} does not declare checkout")
        r = await self.http.post(
            f"{self._endpoint}/checkout",
            json={"lines": lines, "address": address, "approval_ref": approval_ref},
        )
        r.raise_for_status()
        return r.json()

    async def order(self, order_id: str) -> dict:
        r = await self.http.get(f"{self._endpoint}/orders/{order_id}")
        r.raise_for_status()
        return r.json()

    async def delay(self, order_id: str, hours: float = 24) -> dict:
        r = await self.http.post(
            f"{self._endpoint}/admin/orders/{order_id}/delay", json={"hours": hours}
        )
        r.raise_for_status()
        return r.json()
