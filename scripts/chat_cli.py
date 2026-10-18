"""Quick conversational check: python scripts/chat_cli.py [voice|web] "msg1" "msg2" ..."""

import sys
import time

import httpx

ch = sys.argv[1]
msgs = sys.argv[2:]
c = httpx.Client(base_url="http://localhost:8000", timeout=60)
r = c.post("/sessions").json()
sid = r["session_id"]
print("AGENT:", r["greeting"])
for m in msgs:
    t = time.time()
    a = c.post(f"/sessions/{sid}/messages", json={"text": m, "channel": ch}).json()
    print(f"\nYOU:   {m}\nAGENT ({time.time() - t:.1f}s): {a['reply']}")
