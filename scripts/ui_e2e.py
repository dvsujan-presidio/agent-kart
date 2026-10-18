"""Drives the real web UI in headless Chromium through the typed demo and saves screenshots to .run/shots."""

import sys

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:3000"
OUT = ".run/shots"

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1440, "height": 900})
    errors = []
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.goto(URL)
    pg.wait_for_selector("text=Talk to AgentKart")
    pg.wait_for_selector("text=Hi, I'm AgentKart")
    pg.screenshot(path=f"{OUT}/1-start.png")

    def say(text):
        pg.fill("input[placeholder^='Type']", text)
        pg.keyboard.press("Enter")

    def wait_reply(n):  # wait until n assistant bubbles exist and busy dots are gone
        pg.wait_for_function(
            "n => document.querySelectorAll('div.justify-start').length >= n", arg=n, timeout=60000
        )
        pg.wait_for_selector("text=Understanding", state="detached", timeout=60000)

    say(
        "Help me shop for a birthday party for 10 people tomorrow evening, under 3000 rupees. I already have plates."
    )
    wait_reply(2)
    say("chocolate")
    wait_reply(3)
    say("no need for eggless")
    wait_reply(4)
    say("yes use my saved address")
    wait_reply(5)
    pg.wait_for_selector("text=Review & approve order")
    pg.screenshot(path=f"{OUT}/2-basket.png")
    say("make it a premium 1.5 kg cake")
    wait_reply(6)
    pg.wait_for_selector("text=pick a trade-off")
    pg.screenshot(path=f"{OUT}/3-over-budget.png")
    pg.click("button:has-text('Apply') >> nth=0")
    pg.wait_for_selector("text=Review & approve order")
    pg.click("button:has-text('+')")
    pg.wait_for_selector("text=Shares add up")
    pg.screenshot(path=f"{OUT}/4-after-option-split.png")
    pg.click("text=Review & approve order")
    pg.wait_for_selector("text=Approve this exact order")
    pg.screenshot(path=f"{OUT}/5-approval-modal.png")
    pg.click("text=Approve & place order")
    pg.wait_for_selector("text=Simulate cake delay")
    pg.screenshot(path=f"{OUT}/6-ordered.png")
    pg.click("text=Simulate cake delay")
    pg.wait_for_selector("text=Approve backup order", timeout=30000)
    pg.screenshot(path=f"{OUT}/7-fallback.png")
    pg.click("text=Approve & place order")
    pg.wait_for_selector("text=backup, pickup", timeout=15000)
    pg.screenshot(path=f"{OUT}/8-backup-placed.png")
    print("UI flow OK. console errors:", [e for e in errors if "favicon" not in e][:5])
    b.close()
