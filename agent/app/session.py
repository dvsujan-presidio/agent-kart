from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from app.pipeline import PlanResult, PlanState
from contracts.models import Address, Approval, ApprovalRequest, Basket


@dataclass
class Pending:
    """What an open ApprovalRequest is for: the main basket or a fallback backup order."""

    kind: str  # "main" | "backup"
    basket: Basket
    request: ApprovalRequest
    replaces_order: str | None = None


@dataclass
class Session:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    channel: str = "web"
    created: datetime | None = None
    history: list[dict] = field(default_factory=list)
    state: PlanState = field(default_factory=PlanState)
    address: Address | None = None
    asked: set[str] = field(default_factory=set)
    last_question: str | None = None
    plan: PlanResult | None = None
    pending: Pending | None = None
    approval: Approval | None = None
    real_carts: list = field(default_factory=list)  # RealCart objects (real store mode)
    address_draft: dict = field(default_factory=dict)  # parts of a new address collected so far
    awaiting_address: bool = False  # user declined the saved address and owes us a new one
    orders: list[dict] = field(default_factory=list)  # one per store order, kept in sync by tracker
    ordered_hashes: set[str] = field(default_factory=set)
    fallback_done: set[str] = field(default_factory=set)
    events: list[dict] = field(default_factory=list)
    cond: asyncio.Condition = field(default_factory=asyncio.Condition)
    tracker: asyncio.Task | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def emit(self, type_: str, data: dict) -> None:
        async with self.cond:
            self.events.append({"id": len(self.events) + 1, "type": type_, "data": data})
            self.cond.notify_all()


class SessionStore:
    def __init__(self):
        self._s: dict[str, Session] = {}

    def create(self, channel: str = "web") -> Session:
        s = Session(channel=channel)
        self._s[s.id] = s
        return s

    def get(self, sid: str) -> Session | None:
        return self._s.get(sid)

    def all(self) -> list[Session]:
        return list(self._s.values())
