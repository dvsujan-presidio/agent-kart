"""Approval gate. The only place a checkout token is minted or verified.

No LLM-visible tool may call into this module. Voice approvals additionally pass the
deterministic confirmation gate in voice.confirmation.
"""

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta

from contracts.models import Approval, ApprovalRequest, Channel
from voice.confirmation import is_confirmed


class ApprovalError(Exception):
    """Raised for any reason approval/checkout must be refused (maps to HTTP 403)."""


class ApprovalGate:
    def __init__(self, secret: str, ttl_seconds: int = 90):
        self._secret = secret.encode()
        self._ttl = timedelta(seconds=ttl_seconds)
        self._requests: dict[str, dict] = {}

    # --- requests -------------------------------------------------------
    def create_request(
        self, session_id: str, basket_hash: str, readback: str, now: datetime
    ) -> ApprovalRequest:
        # a new request supersedes any pending one for the session
        for r in self._requests.values():
            if r["session_id"] == session_id:
                r["used"] = True
        req = ApprovalRequest(
            request_id=secrets.token_urlsafe(12),
            session_id=session_id,
            basket_hash=basket_hash,
            readback=readback,
            expires_at=now + self._ttl,
        )
        self._requests[req.request_id] = {
            "session_id": session_id,
            "hash": basket_hash,
            "expires_at": req.expires_at,
            "used": False,
        }
        return req

    def invalidate_session(self, session_id: str) -> None:
        """Call on every basket edit."""
        for r in self._requests.values():
            if r["session_id"] == session_id:
                r["used"] = True

    # --- approve --------------------------------------------------------
    def approve(
        self,
        *,
        session_id: str,
        request_id: str,
        current_basket_hash: str,
        channel: Channel,
        now: datetime,
        utterance: str | None = None,
        stt_confidence: float | None = None,
    ) -> Approval:
        r = self._requests.get(request_id)
        if r is None or r["session_id"] != session_id:
            raise ApprovalError("unknown approval request")
        if r["used"]:
            raise ApprovalError("approval request already used or superseded")
        if now >= r["expires_at"]:
            r["used"] = True
            raise ApprovalError("approval request expired")
        if r["hash"] != current_basket_hash:
            r["used"] = True
            raise ApprovalError("basket changed since approval was requested")
        if channel == "voice" and not is_confirmed(utterance, stt_confidence):
            # request stays open: the user may answer again until it expires
            raise ApprovalError("spoken confirmation not clear")
        r["used"] = True
        exp = now + self._ttl
        token = self._sign(
            {"s": session_id, "h": r["hash"], "r": request_id, "c": channel, "exp": exp.timestamp()}
        )
        return Approval(
            basket_hash=r["hash"],
            approved_at=now,
            channel=channel,
            request_id=request_id,
            confirmation_utterance=utterance,
            token=token,
        )

    # --- verify (called by /checkout) -------------------------------------
    def verify(
        self, token: str | None, *, session_id: str, current_basket_hash: str, now: datetime
    ) -> dict:
        if not token:
            raise ApprovalError("missing approval token")
        try:
            body, sig = token.rsplit(".", 1)
            if not hmac.compare_digest(sig, self._mac(body)):
                raise ValueError
            payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        except Exception as e:
            raise ApprovalError("invalid approval token") from e
        if payload["s"] != session_id:
            raise ApprovalError("token belongs to another session")
        if now.timestamp() >= payload["exp"]:
            raise ApprovalError("approval token expired")
        if payload["h"] != current_basket_hash:
            raise ApprovalError("basket changed after approval")
        return payload

    # --- internals --------------------------------------------------------
    def _mac(self, body: str) -> str:
        return hmac.new(self._secret, body.encode(), hashlib.sha256).hexdigest()

    def _sign(self, payload: dict) -> str:
        body = (
            base64.urlsafe_b64encode(json.dumps(payload, sort_keys=True).encode())
            .decode()
            .rstrip("=")
        )
        return f"{body}.{self._mac(body)}"
