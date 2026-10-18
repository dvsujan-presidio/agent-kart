from datetime import UTC, datetime, timedelta

import pytest

from app.approval import ApprovalError, ApprovalGate

T0 = datetime(2026, 10, 17, 18, 0, tzinfo=UTC)
S = "sess1"


def gate():
    return ApprovalGate("secret", ttl_seconds=90)


def request(g, h="H1"):
    return g.create_request(S, h, "readback text", T0)


def approve(g, req, h="H1", channel="web", utterance=None, now=T0):
    return g.approve(
        session_id=S,
        request_id=req.request_id,
        current_basket_hash=h,
        channel=channel,
        now=now,
        utterance=utterance,
    )


def test_happy_path_web():
    g = gate()
    a = approve(g, request(g))
    assert g.verify(a.token, session_id=S, current_basket_hash="H1", now=T0)["c"] == "web"


def test_happy_path_voice():
    g = gate()
    a = approve(g, request(g), channel="voice", utterance="yes, place the order")
    assert a.confirmation_utterance == "yes, place the order"
    g.verify(a.token, session_id=S, current_basket_hash="H1", now=T0)


def test_voice_rejects_unclear_but_request_stays_open():
    g = gate()
    r = request(g)
    with pytest.raises(ApprovalError):
        approve(g, r, channel="voice", utterance="wait actually")
    assert approve(g, r, channel="voice", utterance="yes").token


def test_missing_token():
    with pytest.raises(ApprovalError):
        gate().verify(None, session_id=S, current_basket_hash="H1", now=T0)


def test_tampered_token():
    g = gate()
    a = approve(g, request(g))
    with pytest.raises(ApprovalError):
        g.verify(a.token[:-2] + "00", session_id=S, current_basket_hash="H1", now=T0)


def test_token_expired():
    g = gate()
    a = approve(g, request(g))
    with pytest.raises(ApprovalError):
        g.verify(a.token, session_id=S, current_basket_hash="H1", now=T0 + timedelta(seconds=91))


def test_hash_mismatch_at_checkout():
    g = gate()
    a = approve(g, request(g))
    with pytest.raises(ApprovalError):
        g.verify(a.token, session_id=S, current_basket_hash="H2", now=T0)


def test_hash_mismatch_at_approve():
    g = gate()
    with pytest.raises(ApprovalError):
        approve(g, request(g), h="H2")


def test_edit_invalidates_pending_request():
    g = gate()
    r = request(g)
    g.invalidate_session(S)
    with pytest.raises(ApprovalError):
        approve(g, r)


def test_request_reuse_and_expiry():
    g = gate()
    r = request(g)
    approve(g, r)
    with pytest.raises(ApprovalError):
        approve(g, r)
    r2 = request(g)
    with pytest.raises(ApprovalError):
        approve(g, r2, now=T0 + timedelta(seconds=91))


def test_new_request_supersedes_old():
    g = gate()
    r1 = request(g)
    request(g)
    with pytest.raises(ApprovalError):
        approve(g, r1)


def test_other_session_token_rejected():
    g = gate()
    a = approve(g, request(g))
    with pytest.raises(ApprovalError):
        g.verify(a.token, session_id="other", current_basket_hash="H1", now=T0)
