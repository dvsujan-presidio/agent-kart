"""Serves ONLY the AgentKart UCP agent profile (public JSON, no secrets). Port 8300.

Stores fetch this URL on every request (meta.ucp-agent.profile). UCP requires HTTPS, no redirects and
Cache-Control public with max-age >= 60, so run it behind a tunnel or host the JSON on any static host:
    cloudflared tunnel --url http://localhost:8300
"""

import hashlib
from pathlib import Path

from fastapi import FastAPI, Response

PROFILE = Path(__file__).with_name("agent-profile.json")
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/.well-known/agentkart-agent-profile.json")
@app.get("/agent-profile.json")
def profile() -> Response:
    body = PROFILE.read_bytes()
    return Response(
        body,
        media_type="application/json",
        headers={
            "Cache-Control": "public, max-age=60",
            "ETag": f'"{hashlib.sha256(body).hexdigest()[:16]}"',
        },
    )


@app.get("/health")
def health() -> dict:
    return {"ok": True}
