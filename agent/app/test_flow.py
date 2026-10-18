"""End-to-end birthday story with a scripted NLU and in-process mock stores (no network, no LLM)."""

import time

import pytest
from fastapi.testclient import TestClient

from app.approval import ApprovalGate
from app.config import Settings
from app.main import create_app
from app.nlu import TurnParse
from app.orchestrator import Orchestrator
from app.testing import inproc_clients, tomorrow_at


def tp(**kw) -> TurnParse:
    base = dict(
        intent="provide_info",
        scenario=None,
        guests=None,
        budget_amount=None,
        deadline_iso=None,
        exclusions_add=[],
        exclusions_remove=[],
        cake_flavor=None,
        eggless=None,
        cake_tier=None,
        cake_kg=None,
        use_saved_address=None,
        address_text=None,
        address_area=None,
        address_city=None,
        address_pincode=None,
        store_mode=None,
        goal_summary=None,
        add_items=[],
        payers=None,
        option_index=None,
        drop_categories=[],
    )
    return TurnParse(**(base | kw))


class Scripted:
    def __init__(self, script: dict[str, TurnParse]):
        self.script = script

    async def parse(self, history, ctx):
        return self.script[history[-1]["content"]]


STORY = {
    "plan": tp(
        scenario="birthday_party",
        guests=10,
        budget_amount=3000,
        deadline_iso=tomorrow_at(18).isoformat(),
        exclusions_add=["plates"],
    ),
    "chocolate": tp(cake_flavor="chocolate"),
    "not eggless": tp(eggless=False),
    "yes saved address": tp(use_saved_address=True),
    "premium": tp(intent="edit", cake_tier="premium", cake_kg=1.5),
    "do 1": tp(intent="apply_option", option_index=1),
    "split 4": tp(intent="split", payers=4),
    "place": tp(intent="place_order"),
}


@pytest.fixture
def stack():
    clients, apps = inproc_clients()
    cfg = Settings(approval_hmac_secret="t", demo_mode=True, track_interval_seconds=0.05)
    orch = Orchestrator(
        clients=clients, nlu=Scripted(STORY), gate=ApprovalGate("t", 90), settings=cfg
    )
    with TestClient(create_app(orch, cfg)) as client:
        yield client, orch


def say(c, sid, text, channel="web"):
    r = c.post(f"/sessions/{sid}/messages", json={"text": text, "channel": channel})
    assert r.status_code == 200, r.text
    return r.json()


def test_full_story(stack):
    c, orch = stack
    sid = c.post("/sessions").json()["session_id"]
    # 3 clarifying questions, one at a time
    assert "flavor" in say(c, sid, "plan")["reply"]
    assert "eggless" in say(c, sid, "chocolate")["reply"]
    assert "saved address" in say(c, sid, "not eggless")["reply"]
    r = say(c, sid, "yes saved address")["reply"]
    b = c.get(f"/sessions/{sid}/basket").json()["basket"]
    assert b["total_minor"] == 266500 and len({ln["store_id"] for ln in b["lines"]}) == 2
    assert "saved" in r and b["insight"]["saving_minor"] == 4900
    assert any(n["category"] == "cups" for n in b["late_notes"])
    assert all(ln["category"] != "plates" for ln in b["lines"])
    assert all(ln["on_time"] for ln in b["lines"])
    # premium 1.5 kg goes over budget -> options
    r = say(c, sid, "premium")["reply"]
    b = c.get(f"/sessions/{sid}/basket").json()["basket"]
    assert b["total_minor"] == 326500 and not b["feasible"] and len(b["options"]) >= 2
    assert "Options" in r
    # checkout blocked while over budget
    assert "can't place" in say(c, sid, "place")["reply"]
    say(c, sid, "do 1")
    b = c.get(f"/sessions/{sid}/basket").json()["basket"]
    assert b["feasible"] and b["total_minor"] <= 300000
    assert "each" in say(c, sid, "split 4")["reply"] or "way" in say(c, sid, "split 4")["reply"]
    assert (
        sum(c.get(f"/sessions/{sid}/basket").json()["basket"]["shares_minor"]) == b["total_minor"]
    )

    # no approval -> no checkout
    assert c.post(f"/sessions/{sid}/checkout", json={}).status_code == 403
    placed = say(c, sid, "place", channel="voice")
    req = placed["approval_request"]
    assert req and "rupees" in req["readback"] and placed["reply"] == req["readback"]
    assert c.post(f"/sessions/{sid}/checkout", json={"token": "forged.token"}).status_code == 403
    # voice: hedged answer rejected, request stays open
    bad = c.post(
        f"/sessions/{sid}/approve",
        json={
            "request_id": req["request_id"],
            "channel": "voice",
            "utterance": "wait, change the cake",
        },
    )
    assert bad.status_code == 403
    ok = c.post(
        f"/sessions/{sid}/approve",
        json={
            "request_id": req["request_id"],
            "channel": "voice",
            "utterance": "yes, place the order",
        },
    )
    assert ok.status_code == 200 and ok.json()["channel"] == "voice"
    orders = c.post(f"/sessions/{sid}/checkout", json={"token": ok.json()["token"]}).json()[
        "orders"
    ]
    assert {o["store_id"] for o in orders} == {"cakecorner", "snackmart"}
    # idempotent: second checkout does not double-order
    again = c.post(f"/sessions/{sid}/checkout", json={"token": ok.json()["token"]}).json()["orders"]
    assert len(again) == 2


def _upto_basket(c):
    sid = c.post("/sessions").json()["session_id"]
    for t in ("plan", "chocolate", "not eggless", "yes saved address"):
        say(c, sid, t)
    return sid


def test_edit_after_approval_request_invalidates(stack):
    c, _ = stack
    sid = _upto_basket(c)
    req = say(c, sid, "place")["approval_request"]
    say(c, sid, "premium")  # edit -> replan -> pending cleared
    r = c.post(f"/sessions/{sid}/approve", json={"request_id": req["request_id"], "channel": "web"})
    assert r.status_code == 403


def test_checkout_rejects_token_after_basket_changes(stack):
    c, _ = stack
    sid = _upto_basket(c)
    req = say(c, sid, "place")["approval_request"]
    tok = c.post(
        f"/sessions/{sid}/approve", json={"request_id": req["request_id"], "channel": "web"}
    ).json()["token"]
    say(c, sid, "premium")
    assert c.post(f"/sessions/{sid}/checkout", json={"token": tok}).status_code == 403


def test_delay_triggers_fallback_with_own_approval(stack):
    c, orch = stack
    sid = _upto_basket(c)
    req = say(c, sid, "place")["approval_request"]
    tok = c.post(
        f"/sessions/{sid}/approve", json={"request_id": req["request_id"], "channel": "web"}
    ).json()["token"]
    c.post(f"/sessions/{sid}/checkout", json={"token": tok})
    assert (
        c.post("/demo/delay", json={"session_id": sid, "store_id": "cakecorner"}).status_code == 200
    )
    pending = None
    for _ in range(80):
        time.sleep(0.05)
        pending = c.get(f"/sessions/{sid}").json()["pending"]
        if pending:
            break
    assert pending and pending["kind"] == "backup" and "backup" in pending["readback"]
    s = c.app.state.sessions.get(sid)
    assert s.pending.basket.lines[0].offer.store_id == "nearbybakery"
    ev = [e for e in s.events if e["type"] == "fallback"]
    assert ev and ev[0]["data"]["option"]["store_id"] == "nearbybakery"
    # the main approval token cannot place the backup order
    r = c.post(f"/sessions/{sid}/checkout", json={"token": tok})
    assert r.status_code == 403
    # backup gets its own approval and checkout
    a = c.post(
        f"/sessions/{sid}/approve",
        json={"request_id": pending["request_id"], "channel": "voice", "utterance": "yes"},
    ).json()
    o = c.post(f"/sessions/{sid}/checkout", json={"token": a["token"]}).json()["orders"]
    assert o[0]["store_id"] == "nearbybakery" and o[0]["kind"] == "backup"
