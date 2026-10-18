"""AgentKart API (FastAPI). Routes are documented in docs/api.md."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.approval import ApprovalError, ApprovalGate
from app.config import Settings, get_settings
from app.orchestrator import CheckoutError, Orchestrator
from app.session import Session, SessionStore
from app.ucp_client import StoreClient
from contracts.models import VoiceSession

VOICE_AGENT_NAME = "agentkart-voice"


class NewSession(BaseModel):
    channel: str = "web"


class Message(BaseModel):
    text: str
    channel: str | None = None


class ApproveBody(BaseModel):
    request_id: str
    channel: str = "web"
    utterance: str | None = None
    stt_confidence: float | None = None


class CheckoutBody(BaseModel):
    token: str | None = None


class EditBody(BaseModel):
    action: str  # apply_option | remove
    index: int | None = None
    category: str | None = None


class SplitBody(BaseModel):
    payers: int


class DelayBody(BaseModel):
    session_id: str
    store_id: str = "cakecorner"
    hours: float = 24


def create_app(orch: Orchestrator | None = None, settings: Settings | None = None) -> FastAPI:
    cfg = settings or get_settings()
    store = SessionStore()
    state: dict = {"orch": orch}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        http = None
        if state["orch"] is None:
            from app.converse import LLMConverser
            from app.nlu import LLMNLU  # imported lazily so the API can import without model config
            from app.planner import LLMPlanner
            from app.real_stores.service import RealStoreService

            http = httpx.AsyncClient(timeout=10)
            real_http = httpx.AsyncClient(timeout=20, follow_redirects=False)
            state["real_http"] = real_http
            clients = [StoreClient(u.strip(), http) for u in cfg.store_urls.split(",") if u.strip()]
            state["orch"] = Orchestrator(
                clients=clients,
                nlu=LLMNLU(),
                converser=LLMConverser(),
                real=RealStoreService(cfg, real_http),
                planner=LLMPlanner(),
                gate=ApprovalGate(cfg.approval_hmac_secret, cfg.approval_ttl_seconds),
                settings=cfg,
            )
        yield
        if http:
            await http.aclose()
        if state.get("real_http"):
            await state["real_http"].aclose()

    app = FastAPI(title="AgentKart API", version="0.2.0", lifespan=lifespan)
    app.state.sessions = store
    app.state.holder = state
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[cfg.web_url, "http://127.0.0.1:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def get_orch() -> Orchestrator:
        return state["orch"]

    def sess(sid: str) -> Session:
        s = store.get(sid)
        if s is None:
            raise HTTPException(404, "unknown session")
        return s

    @app.exception_handler(ApprovalError)
    async def _approval_denied(_: Request, e: ApprovalError):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=403, content={"detail": str(e)})

    @app.exception_handler(CheckoutError)
    async def _checkout_failed(_: Request, e: CheckoutError):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=409, content={"detail": str(e)})

    @app.get("/health")
    def health() -> dict:
        return {
            "status": "ok",
            "voice_mode": cfg.voice_mode,
            "model_configured": bool(cfg.model_api_key),
        }

    @app.get("/real/config")
    def real_config() -> dict:
        real = state["orch"].real if state.get("orch") else None
        return {
            "enabled": bool(cfg.real_store_mode),
            "scenarios": [x.strip() for x in cfg.real_store_scenarios.split(",") if x.strip()],
            "search": cfg.real_store_search,
            "cart": cfg.real_store_cart,
            "handoff": cfg.real_store_handoff,
            "replay": cfg.real_store_replay,
            "profile_url": cfg.agent_profile_url,
            "available": bool(real and real.available),
            "never_orders": True,  # real stores get carts only; the MCP client refuses checkout tools
        }

    @app.post("/sessions")
    async def new_session(body: NewSession | None = None) -> dict:
        s = store.create((body or NewSession()).channel)
        s.created = get_orch().clock()
        await s.emit("session_started", {"session_id": s.id})
        greeting = await get_orch().greet(s)
        return {"session_id": s.id, "greeting": greeting}

    @app.post("/sessions/{sid}/messages")
    async def message(sid: str, body: Message) -> dict:
        s = sess(sid)
        reply = await get_orch().handle_message(s, body.text, body.channel)
        return {
            "reply": reply.text,
            "approval_request": reply.approval_request.model_dump(mode="json")
            if reply.approval_request
            else None,
        }

    @app.get("/sessions/{sid}/events")
    async def events(sid: str, request: Request, after: int = 0):
        s = sess(sid)
        last = request.headers.get("last-event-id")
        cursor = int(last) if last and last.isdigit() else after

        async def gen():
            nonlocal cursor
            while True:
                if await request.is_disconnected():
                    return
                async with s.cond:
                    if cursor >= len(s.events):
                        try:
                            await asyncio.wait_for(s.cond.wait(), timeout=15)
                        except TimeoutError:
                            yield {"comment": "keepalive"}
                            continue
                    batch = s.events[cursor:]
                for ev in batch:
                    cursor = ev["id"]
                    yield {"id": str(ev["id"]), "event": ev["type"], "data": json.dumps(ev["data"])}

        return EventSourceResponse(gen())

    @app.get("/sessions/{sid}")
    def snapshot(sid: str) -> dict:
        s = sess(sid)
        o = get_orch()
        return {
            "session_id": s.id,
            "channel": s.channel,
            "basket": o.plan_view(s),
            "orders": s.orders,
            "history": s.history,
            "events": len(s.events),
            "pending": (
                {
                    "kind": s.pending.kind,
                    "request_id": s.pending.request.request_id,
                    "readback": s.pending.request.readback,
                }
                if s.pending
                else None
            ),
            "approved": s.approval is not None,
        }

    @app.get("/sessions/{sid}/basket")
    def basket(sid: str) -> dict:
        return {"basket": get_orch().plan_view(sess(sid))}

    @app.post("/sessions/{sid}/basket/edit")
    async def edit(sid: str, body: EditBody) -> dict:
        s = sess(sid)
        async with s.lock:
            if body.action == "apply_option":
                r = await get_orch()._apply_option(s, body.index)
            elif body.action == "remove" and body.category:
                s.state.dropped.add(body.category)
                r = type("R", (), {"text": await get_orch()._replan(s)})()
            else:
                raise HTTPException(400, "unsupported edit")
        return {"reply": r.text, "basket": get_orch().plan_view(s)}

    @app.post("/sessions/{sid}/split")
    async def split(sid: str, body: SplitBody) -> dict:
        s = sess(sid)
        if not 1 <= body.payers <= 50:
            raise HTTPException(400, "payers must be 1..50")
        s.state.payers = body.payers  # no replan needed: total is unchanged
        view = get_orch().plan_view(s)
        if view:
            await s.emit("basket_updated", view)
        return {"basket": view}

    @app.post("/sessions/{sid}/handoff")
    async def handoff(sid: str) -> dict:
        """Real stores: add the basket to carts at each store and return the continue links."""
        s = sess(sid)
        async with s.lock:
            if not s.plan or not get_orch()._is_real(s):
                raise HTTPException(409, "no real-store basket to add to carts")
            r = await get_orch()._real_handoff(s)
        return {"reply": r.text, "carts": [get_orch().cart_json(c) for c in s.real_carts]}

    @app.get("/sessions/{sid}/real/carts")
    def real_carts(sid: str) -> dict:
        return {"carts": [c.model_dump(mode="json") for c in sess(sid).real_carts]}

    @app.post("/sessions/{sid}/approval-request")
    async def approval_request(sid: str) -> dict:
        s = sess(sid)
        async with s.lock:
            r = await get_orch()._place_order(s)
        if r.approval_request is None:
            raise HTTPException(409, r.text)
        return r.approval_request.model_dump(mode="json")

    @app.post("/sessions/{sid}/approve")
    async def approve(sid: str, body: ApproveBody) -> dict:
        s = sess(sid)
        a = get_orch().approve(
            s,
            request_id=body.request_id,
            channel=body.channel,
            utterance=body.utterance,
            stt_confidence=body.stt_confidence,
        )
        await get_orch().announce_approved(s, a)
        return a.model_dump(mode="json")

    @app.post("/sessions/{sid}/checkout")
    async def checkout(sid: str, body: CheckoutBody) -> dict:
        return {"orders": await get_orch().checkout(sess(sid), body.token)}

    @app.get("/sessions/{sid}/orders")
    def orders(sid: str) -> dict:
        return {"orders": sess(sid).orders}

    @app.get("/sessions/{sid}/summary")
    def summary(sid: str) -> dict:
        return get_orch().summary(sess(sid))

    @app.post("/sessions/{sid}/voice")
    def voice(sid: str) -> dict:
        sess(sid)
        if not (
            cfg.voice_mode and cfg.livekit_url and cfg.livekit_api_key and cfg.livekit_api_secret
        ):
            raise HTTPException(503, "voice is not configured (LIVEKIT_* in .env)")
        from livekit import api as lk

        token = (
            lk.AccessToken(cfg.livekit_api_key, cfg.livekit_api_secret)
            .with_identity(f"user-{sid}")
            .with_name("You")
            .with_grants(lk.VideoGrants(room_join=True, room=sid))
            .with_room_config(
                lk.RoomConfiguration(
                    agents=[lk.RoomAgentDispatch(agent_name=VOICE_AGENT_NAME, metadata=sid)]
                )
            )
            .to_jwt()
        )
        return VoiceSession(
            livekit_url=cfg.livekit_url,
            room=sid,
            participant_token=token,
            agent_name=VOICE_AGENT_NAME,
        ).model_dump()

    @app.post("/demo/delay")
    async def demo_delay(body: DelayBody) -> dict:
        if not cfg.demo_mode:
            raise HTTPException(403, "demo mode is off")
        return await get_orch().demo_delay(sess(body.session_id), body.store_id, body.hours)

    @app.post("/demo/reset")
    async def demo_reset() -> dict:
        if not cfg.demo_mode:
            raise HTTPException(403, "demo mode is off")
        for c in get_orch().clients.values():
            with __import__("contextlib").suppress(Exception):
                await c.http.post(f"{c.base_url}/admin/reset")
        for s in store.all():
            if s.tracker:
                s.tracker.cancel()
        store._s.clear()
        return {"ok": True}

    return app


app = create_app()
