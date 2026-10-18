"""HTTP/SSE bridge from the voice worker to the AgentKart API. No LLM, no audio."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx


class ApiBridge:
    def __init__(self, base_url: str, session_id: str, http: httpx.AsyncClient | None = None):
        self.base = base_url.rstrip("/")
        self.sid = session_id
        self.http = http or httpx.AsyncClient(timeout=60)

    async def message(self, text: str) -> dict:
        r = await self.http.post(
            f"{self.base}/sessions/{self.sid}/messages", json={"text": text, "channel": "voice"}
        )
        r.raise_for_status()
        return r.json()

    async def approve(
        self, request_id: str, utterance: str, confidence: float | None
    ) -> tuple[int, dict]:
        r = await self.http.post(
            f"{self.base}/sessions/{self.sid}/approve",
            json={
                "request_id": request_id,
                "channel": "voice",
                "utterance": utterance,
                "stt_confidence": confidence,
            },
        )
        return r.status_code, r.json()

    async def checkout(self, token: str) -> list[dict]:
        r = await self.http.post(f"{self.base}/sessions/{self.sid}/checkout", json={"token": token})
        r.raise_for_status()
        return r.json()["orders"]

    async def greeting(self) -> str | None:
        """The assistant's opening line, created by the API when the session started."""
        r = await self.http.get(f"{self.base}/sessions/{self.sid}")
        if r.status_code != 200:
            return None
        first = next(
            (m["content"] for m in r.json().get("history", []) if m["role"] == "assistant"), None
        )
        return first

    async def event_cursor(self) -> int:
        r = await self.http.get(f"{self.base}/sessions/{self.sid}")
        r.raise_for_status()
        return int(r.json().get("events", 0))

    async def events(self, after: int) -> AsyncIterator[tuple[str, dict]]:
        """Minimal SSE client: yields (event_type, data) for events after `after`."""
        async with self.http.stream(
            "GET", f"{self.base}/sessions/{self.sid}/events", params={"after": after}, timeout=None
        ) as r:
            etype, data = "message", ""
            async for line in r.aiter_lines():
                if line.startswith("event:"):
                    etype = line[6:].strip()
                elif line.startswith("data:"):
                    data += line[5:].strip()
                elif line == "" and data:
                    try:
                        yield etype, json.loads(data)
                    except json.JSONDecodeError:
                        pass
                    etype, data = "message", ""
