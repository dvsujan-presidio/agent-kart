"""Real Store Mode through the web UI (LIVE network, US VPN): plan -> basket -> add to carts."""

import sys

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:3000"
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1440, "height": 950})
    errors = []
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.goto(URL)
    pg.wait_for_selector("text=Hi, I'm AgentKart")
    pg.fill(
        "input[placeholder^='Type']",
        "Plan a camping weekend for 4 of us, leaving Friday, budget 4000 dollars",
    )
    pg.keyboard.press("Enter")
    pg.wait_for_selector("text=Real US stores", timeout=120000)
    pg.wait_for_selector("text=Add to carts at each store", timeout=60000)
    pg.screenshot(path=".run/shots/r1-real-basket.png")
    pg.click("text=Add to carts at each store")
    pg.wait_for_selector("text=nothing has been ordered", timeout=90000)
    pg.wait_for_selector("text=Open cart", timeout=10000)
    links = pg.eval_on_selector_all("a:has-text('Open cart')", "els => els.map(e => e.href)")
    pg.evaluate("document.querySelector('section.overflow-y-auto').scrollTo(0, 99999)")
    pg.wait_for_timeout(500)
    pg.screenshot(path=".run/shots/r2-real-carts.png", full_page=False)
    print("cart links:", [link[:60] for link in links])
    print("UI real flow OK; console errors:", [e for e in errors if "favicon" not in e][:3])
    b.close()
