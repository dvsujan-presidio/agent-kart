"""Run the demo story against the running API with the real model: python scripts/demo_cli.py

Voice approval is simulated by posting the spoken utterance to /approve with channel=voice,
exactly what the LiveKit worker does.
"""

import sys
import time

import httpx

API = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
c = httpx.Client(base_url=API, timeout=60)


def say(sid, text, channel="web"):
    t = time.time()
    r = c.post(f"/sessions/{sid}/messages", json={"text": text, "channel": channel}).json()
    print(
        f"\n\033[1mYOU\033[0m   {text}\n\033[1mAGENT\033[0m ({time.time() - t:.1f}s) {r['reply']}"
    )
    return r


def basket(sid):
    b = c.get(f"/sessions/{sid}/basket").json()["basket"]
    print("   ── basket ──")
    for ln in b["lines"]:
        print(
            f"   {ln['store_name']:12s} {ln['title'][:38]:38s} x{ln['packs']}  ₹{ln['line_total_minor'] / 100:>7,.0f}  {ln['rule']}"
        )
    print(
        f"   fees {b['fees']}  TOTAL ₹{b['total_minor'] / 100:,.0f} / budget ₹{b['budget_minor'] / 100:,.0f}"
        f"  feasible={b['feasible']}"
    )
    return b


sid = c.post("/sessions").json()["session_id"]
print("session", sid)
say(
    sid,
    "Help me shop for a birthday party for 10 people tomorrow evening, under three thousand rupees. I already have plates.",
    "voice",
)
say(sid, "Chocolate.", "voice")
say(sid, "No, it doesn't need to be eggless.", "voice")
say(sid, "Yes, use my saved address.", "voice")
basket(sid)
say(sid, "Make it a premium 1.5 kg cake.", "voice")
basket(sid)
say(sid, "Do that one.", "voice")
basket(sid)
say(sid, "Four of us are splitting this.", "voice")
r = say(sid, "Okay, place the order.", "voice")
req = r["approval_request"]
for utt in ("Wait, actually change the cake", "Yes, place the order"):
    a = c.post(
        f"/sessions/{sid}/approve",
        json={"request_id": req["request_id"], "channel": "voice", "utterance": utt},
    )
    print(
        f"\n\033[1mYOU (spoken)\033[0m {utt!r} -> HTTP {a.status_code} {a.json().get('detail', 'APPROVED')}"
    )
    if a.status_code == 200:
        break
orders = c.post(f"/sessions/{sid}/checkout", json={"token": a.json()["token"]}).json()["orders"]
for o in orders:
    print(
        f"   ORDER {o['order_id']} {o['store_name']:12s} ₹{o['total_minor'] / 100:,.0f} {o['status']} eta {o['eta'][:16]}"
    )
print("\n-- simulate cake delay --")
c.post("/demo/delay", json={"session_id": sid, "store_id": "cakecorner"})
for _ in range(20):
    time.sleep(1)
    snap = c.get(f"/sessions/{sid}").json()
    if snap["pending"]:
        print("\033[1mAGENT (proactive)\033[0m", snap["pending"]["readback"])
        a = c.post(
            f"/sessions/{sid}/approve",
            json={
                "request_id": snap["pending"]["request_id"],
                "channel": "voice",
                "utterance": "yes",
            },
        ).json()
        o = c.post(f"/sessions/{sid}/checkout", json={"token": a["token"]}).json()["orders"]
        print(
            "   BACKUP ORDER",
            o[0]["order_id"],
            o[0]["store_name"],
            f"₹{o[0]['total_minor'] / 100:,.0f}",
        )
        break
