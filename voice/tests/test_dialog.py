import pytest

from voice.dialog import AWAIT_CONFIRM, GATHER, VoiceDialog


class FakeBridge:
    def __init__(self):
        self.calls: list[tuple] = []
        self.approve_result = (200, {"token": "tok"})
        self.msg = {"reply": "ok", "approval_request": None}

    async def message(self, text):
        self.calls.append(("message", text))
        return self.msg

    async def approve(self, rid, utt, conf):
        self.calls.append(("approve", rid, utt))
        return self.approve_result

    async def checkout(self, token):
        self.calls.append(("checkout", token))
        return [
            {"store_name": "CakeCorner", "kind": "main"},
            {"store_name": "SnackMart", "kind": "main"},
        ]


REQ = {
    "reply": "Two thousand rupees. Shall I place the order?",
    "approval_request": {"request_id": "r1", "readback": "Two thousand rupees."},
}


@pytest.mark.asyncio
async def test_readback_is_server_text_and_enters_confirm():
    b = FakeBridge()
    b.msg = REQ
    d = VoiceDialog(b)
    assert await d.handle_user_turn("place the order") == REQ["reply"]
    assert d.state == AWAIT_CONFIRM and d.pending_id == "r1"


@pytest.mark.asyncio
async def test_confirm_goes_to_approve_not_to_llm_then_checkout():
    b = FakeBridge()
    b.msg = REQ
    d = VoiceDialog(b)
    await d.handle_user_turn("place the order")
    b.calls.clear()
    out = await d.handle_user_turn("yes, place the order", 0.9)
    assert [c[0] for c in b.calls] == ["approve", "checkout"]  # never "message"
    assert "2 orders" in out and "CakeCorner and SnackMart" in out and d.state == GATHER


@pytest.mark.asyncio
async def test_hedged_answer_places_nothing_and_continues_normally():
    b = FakeBridge()
    b.msg = REQ
    d = VoiceDialog(b)
    await d.handle_user_turn("place the order")
    b.approve_result = (403, {"detail": "spoken confirmation not clear"})
    b.msg = {"reply": "Which cake?", "approval_request": None}
    b.calls.clear()
    out = await d.handle_user_turn("wait, change the cake")
    assert "nothing is ordered" in out and out.endswith("Which cake?")
    assert [c[0] for c in b.calls] == ["approve", "message"] and not any(
        c[0] == "checkout" for c in b.calls
    )
    assert d.state == GATHER


@pytest.mark.asyncio
async def test_expired_request_message():
    b = FakeBridge()
    b.msg = REQ
    d = VoiceDialog(b)
    await d.handle_user_turn("place the order")
    b.approve_result = (403, {"detail": "approval request expired"})
    assert "timed out" in await d.handle_user_turn("yes")


def test_events_ui_approval_and_backup_announce():
    d = VoiceDialog(FakeBridge())
    assert (
        d.on_event("approval_requested", {"request_id": "x", "readback": "Total. Shall I?"})
        == "Total. Shall I?"
    )
    assert d.state == AWAIT_CONFIRM
    d2 = VoiceDialog(FakeBridge())
    out = d2.on_event(
        "approval_requested", {"request_id": "b1", "readback": "rb", "announce": "Heads up. rb"}
    )
    assert out == "Heads up. rb" and d2.pending_id == "b1"
    assert d2.on_event("approval_requested", {"request_id": "b1", "readback": "rb"}) is None
    d2.on_event("approved", {"channel": "web"})
    assert d2.state == GATHER


def test_fallback_without_option_is_spoken():
    d = VoiceDialog(FakeBridge())
    assert d.on_event("fallback", {"text": "delayed", "option": None}) == "delayed"
    assert d.on_event("fallback", {"text": "x", "option": {"store_id": "n"}}) is None
