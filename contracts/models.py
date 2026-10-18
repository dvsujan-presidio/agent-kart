"""Shared contracts (source of truth). Money is integer minor units + currency."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Currency = Literal["INR", "USD"]
Channel = Literal["web", "voice"]


class Address(BaseModel):
    line1: str
    area: str | None = None
    city: str = ""
    pincode: str = ""
    country: str = "IN"


class Discount(BaseModel):
    code: str
    amount_minor: int


class Goal(BaseModel):
    scenario: str
    occasion: str
    guests: int
    budget_minor: int
    currency: Currency
    deadline: datetime
    address: Address | None = None
    exclusions: list[str] = Field(default_factory=list)
    preferences: dict = Field(default_factory=dict)
    payers: int = 1


class ListItem(BaseModel):
    category: str
    need_qty: float
    unit: str
    rule: str
    required: bool = True


class Offer(BaseModel):
    store_id: str
    source: Literal["ucp_mock", "ucp_real"]
    product_id: str
    variant_id: str
    title: str
    category: str
    pack_size: float
    unit: str
    price_minor: int
    currency: Currency
    rating: float | None = None
    eta: datetime | None = None
    in_stock: bool = True
    discount: Discount | None = None
    url: str | None = None
    attributes: dict[str, str | bool | int | float] = Field(default_factory=dict)
    pickup_only: bool = False


class StoreTerms(BaseModel):
    store_id: str
    delivery_fee_minor: int | None = None  # None = unknown until store checkout
    free_delivery_above_minor: int | None = None
    min_order_minor: int | None = None


class BasketLine(BaseModel):
    offer: Offer
    packs: int
    line_total_minor: int


class Exclusion(BaseModel):
    offer: Offer
    reason: Literal["late", "out_of_stock", "user_excluded"]


class Basket(BaseModel):
    lines: list[BasketLine]
    fees_by_store: dict[str, int | None]
    discounts_minor: int = 0
    total_minor: int
    total_is_estimate: bool = False
    budget_minor: int
    currency: Currency
    excluded: list[Exclusion] = Field(default_factory=list)
    feasible: bool = True
    tradeoffs: list[TradeOff] = Field(default_factory=list)
    hash: str


class TradeOff(BaseModel):
    title: str
    delta_minor: int  # negative = saving
    basket: Basket


class ApprovalRequest(BaseModel):
    request_id: str
    session_id: str
    basket_hash: str
    readback: str  # built in Python from the Basket; spoken verbatim
    expires_at: datetime


class Approval(BaseModel):
    basket_hash: str
    approved_at: datetime
    channel: Channel
    request_id: str
    confirmation_utterance: str | None = None
    token: str


class VoiceSession(BaseModel):
    livekit_url: str
    room: str
    participant_token: str
    agent_name: str = "agentkart-voice"


class Split(BaseModel):
    payers: int
    shares_minor: list[int]


class OrderStatus(BaseModel):
    store_id: str
    order_id: str
    status: Literal["placed", "packed", "out_for_delivery", "delayed", "delivered"]
    eta: datetime


class RealCart(BaseModel):
    store_id: str
    store_domain: str
    ucp_cart_id: str | None = None
    lines: list[BasketLine]
    subtotal_minor: int
    shipping_estimate_minor: int | None = None
    currency: Currency = "USD"
    handoff_url: str | None = None
    handoff_kind: Literal["cart_continue_url", "permalink"] | None = None
    degraded: list[str] = Field(default_factory=list)


class PriceCheck(BaseModel):
    retailer: str
    query: str
    indicative_price_minor: int | None = None
    currency: Currency = "USD"
    source_url: str
    snippet: str
    is_estimate: bool = True


Basket.model_rebuild()
TradeOff.model_rebuild()
