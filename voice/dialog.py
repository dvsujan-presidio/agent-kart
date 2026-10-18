"""Voice dialog state machine (pure logic; the LiveKit worker only supplies audio).

States: GATHER (normal turns go to the AgentKart orchestrator) and AWAIT_CONFIRM (the next
final user transcript is NOT sent to any LLM: it is posted to /approve, where deterministic
Python decides whether it is a clear yes). The read-back text spoken is the server's, verbatim.
"""

from __future__ import annotations

from typing import Protocol

GATHER, AWAIT_CONFIRM = "GATHER", "AWAIT_CONFIRM"


class Bridge(Protocol):
    async def message(self, text: str) -> dict: ...
    async def approve(
        self, request_id: str, utterance: str, confidence: float | None
    ) -> tuple[int, dict]: ...
    async def checkout(self, token: str) -> list[dict]: ...


def confirmation_text(orders: list[dict]) -> str:
    if not orders:
        return "Done."
    if all(o.get("kind") == "backup" for o in orders):
        return (
            f"Backup order placed with {orders[0]['store_name']} for pickup. I'll keep tracking it."
        )
    names = [o["store_name"] for o in orders]
    joined = " and ".join(names) if len(names) <= 2 else ", ".join(names[:-1]) + f" and {names[-1]}"
    n = len(orders)
    return (
        f"Done. I've placed {n} order{'s' if n != 1 else ''} with {joined}. "
        "I'll tell you if anything gets delayed."
    )


class VoiceDialog:
    def __init__(self, bridge: Bridge):
        self.bridge = bridge
        self.state = GATHER
        self.pending_id: str | None = None

    def _track(self, reply: dict) -> None:
        req = reply.get("approval_request")
        if req:
            self.state, self.pending_id = AWAIT_CONFIRM, req["request_id"]

    async def handle_user_turn(self, text: str, confidence: float | None = None) -> str:
        """Returns what the agent should say."""
        if self.state == AWAIT_CONFIRM and self.pending_id:
            status, body = await self.bridge.approve(self.pending_id, text, confidence)
            if status == 200:
                orders = await self.bridge.checkout(body["token"])
                self.state, self.pending_id = GATHER, None
                return confirmation_text(orders)
            detail = str(body.get("detail", ""))
            self.state, self.pending_id = GATHER, None
            if "expired" in detail or "no matching" in detail or "already used" in detail:
                return (
                    "That approval timed out, so nothing was ordered. "
                    "Say place the order whenever you're ready."
                )
            # not a clear yes: treat it as a normal request (e.g. "wait, change the cake")
            reply = await self.bridge.message(text)
            self._track(reply)
            return "No problem, nothing is ordered yet. " + reply["reply"]
        reply = await self.bridge.message(text)
        self._track(reply)
        return reply["reply"]

    def on_event(self, etype: str, data: dict) -> str | None:
        """Server-pushed events. Returns text to say proactively, if any."""
        if etype == "approval_requested":
            if data.get("request_id") == self.pending_id:
                return None  # we asked for it ourselves and already spoke the read-back
            self.state, self.pending_id = AWAIT_CONFIRM, data["request_id"]
            return data.get("announce") or data["readback"]
        if etype == "fallback" and not data.get("option"):
            return data.get("text")
        if etype == "approved" and data.get("channel") == "web":
            self.state, self.pending_id = GATHER, None
        return None
