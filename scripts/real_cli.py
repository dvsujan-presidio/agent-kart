"""Live real-store demo through the API: python scripts/real_cli.py "<first message>" [channel]"""

import sys
import time

import httpx

c = httpx.Client(base_url="http://localhost:8000", timeout=120)
sid = c.post("/sessions").json()["session_id"]


def say(m, ch="web"):
    t = time.time()
    a = c.post(f"/sessions/{sid}/messages", json={"text": m, "channel": ch}).json()
    print(f"\nYOU: {m}\nAGENT ({time.time() - t:.1f}s): {a['reply']}")


for m in [a for a in sys.argv[1:] if not a.startswith("--")]:
    say(m)
b = c.get(f"/sessions/{sid}/basket").json()["basket"]
if b:
    print(
        f"\nmode={b['mode']} total=${b['total_minor'] / 100:,.2f} budget=${b['budget_minor'] / 100:,.2f} estimate={b['estimate']} feasible={b['feasible']}"
    )
    for ln in b["lines"]:
        print(
            f"  {ln['store_name']:22s} {ln['title'][:52]:52s} x{ln['packs']} ${ln['line_total_minor'] / 100:>8,.2f}  {ln['rule']}"
        )
    if b["feasible"] and "--carts" in sys.argv:
        r = c.post(f"/sessions/{sid}/handoff").json()
        print("\nCARTS:")
        for k in r["carts"]:
            print(
                f"  {k['store_id']:10s} subtotal=${k['subtotal_minor'] / 100:,.2f} degraded={k['degraded']} link={(k['handoff_url'] or '')[:70]}"
            )
        print("AGENT:", r["reply"])
        print(
            "checkout attempt ->",
            c.post(f"/sessions/{sid}/checkout", json={"token": None}).status_code,
            "(must be 403/409)",
        )
