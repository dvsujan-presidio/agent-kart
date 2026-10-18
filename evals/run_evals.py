"""Deterministic evals: many generated scenarios through the real pipeline (no LLM, in-process stores).

    make eval      ->  evals/report/index.html + results.csv

Metrics that must be 100%: budget compliance when feasible, no late items, exclusions respected,
quantity sufficiency, split sums exactly, no mixed currencies, checkout blocked without approval,
approval invalidated by edits, optimality vs brute force.
"""

import asyncio
import csv
import itertools
import random
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "agent")]

from app.approval import ApprovalError, ApprovalGate  # noqa: E402
from app.pipeline import PlanState, build_plan  # noqa: E402
from app.testing import inproc_clients, tomorrow_at  # noqa: E402

from domain.optimizer import _candidates, evaluate  # noqa: E402
from domain.quantities import packs_needed  # noqa: E402
from domain.split import split_equal  # noqa: E402

IST = ZoneInfo("Asia/Kolkata")
OUT = Path(__file__).parent / "report"
METRICS = [
    "budget_compliance",
    "no_late_items",
    "exclusions_respected",
    "quantity_sufficiency",
    "split_exact",
    "single_currency",
    "optimal_vs_bruteforce",
    "checkout_needs_approval",
    "edit_invalidates_approval",
]


def brute_total(pr, st) -> int | None:
    cands = [
        row
        for row in _candidates(
            pr.items,
            [
                o
                for o in pr.offers
                if o.eta is None or o.eta <= st.deadline - __import__("datetime").timedelta(hours=2)
            ],
        )
        if row
    ]
    best = None
    for combo in itertools.product(*cands):
        total, _, _, valid = evaluate(list(combo), pr.terms)
        if valid and (best is None or total < best):
            best = total
    return best


async def run() -> list[dict]:
    clients, _ = inproc_clients()
    rng = random.Random(42)
    scenarios = []
    for guests, budget, excl, flavor, tier in itertools.product(
        [4, 10, 25],
        [150000, 300000, 600000],
        [(), ("plates",), ("plates", "party_hats")],
        ["chocolate", "vanilla"],
        ["standard", "premium"],
    ):
        scenarios.append(
            dict(
                guests=guests,
                budget=budget,
                excl=set(excl),
                flavor=flavor,
                tier=tier,
                eggless=rng.random() < 0.3,
            )
        )
    rows = []
    gate = ApprovalGate("eval-secret", 90)
    now = datetime.now(IST)
    for n, sc in enumerate(scenarios):
        st = PlanState(
            guests=sc["guests"],
            budget_minor=sc["budget"],
            deadline=tomorrow_at(18),
            exclusions=set(sc["excl"]),
            prefs={"cake_flavor": sc["flavor"], "cake_tier": sc["tier"], "eggless": sc["eggless"]},
        )
        pr = await build_plan(st, clients)
        b = pr.basket
        r = {
            "id": n,
            **{k: sc[k] for k in ("guests", "budget", "flavor", "tier", "eggless")},
            "excl": ",".join(sorted(sc["excl"])),
            "total": b.total_minor,
            "feasible": b.feasible,
        }
        items = {i.category: i for i in pr.items}
        r["budget_compliance"] = (not b.feasible) or b.total_minor <= b.budget_minor
        r["no_late_items"] = all(
            ln.offer.eta is None
            or ln.offer.eta <= st.deadline - __import__("datetime").timedelta(hours=2)
            for ln in b.lines
        )
        r["exclusions_respected"] = all(ln.offer.category not in sc["excl"] for ln in b.lines)
        r["quantity_sufficiency"] = all(
            (
                packs_needed(
                    items[ln.offer.category].need_qty,
                    items[ln.offer.category].unit,
                    ln.offer.pack_size,
                    ln.offer.unit,
                )
                or 0
            )
            <= ln.packs
            for ln in b.lines
        )
        shares = split_equal(b.total_minor, rng.randint(2, 7))
        r["split_exact"] = sum(shares) == b.total_minor and max(shares) - min(shares) <= 1
        r["single_currency"] = len({ln.offer.currency for ln in b.lines}) <= 1
        want = brute_total(pr, st)
        r["optimal_vs_bruteforce"] = (
            want is None or pr.result.missing_required or b.total_minor == want
        )
        # approval gate: no token, wrong hash, edit invalidates
        sid = f"s{n}"
        try:
            gate.verify(None, session_id=sid, current_basket_hash=b.hash, now=now)
            r["checkout_needs_approval"] = False
        except ApprovalError:
            r["checkout_needs_approval"] = True
        req = gate.create_request(sid, b.hash, "rb", now)
        gate.invalidate_session(sid)  # what every basket edit does
        try:
            gate.approve(
                session_id=sid,
                request_id=req.request_id,
                current_basket_hash=b.hash,
                channel="web",
                now=now,
            )
            r["edit_invalidates_approval"] = False
        except ApprovalError:
            r["edit_invalidates_approval"] = True
        rows.append(r)
    return rows


def report(rows: list[dict]) -> None:
    OUT.mkdir(exist_ok=True)
    with open(OUT / "results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    n = len(rows)
    summary = {m: sum(1 for r in rows if r[m]) for m in METRICS}
    cells = "".join(
        f"<tr><td>{m.replace('_', ' ')}</td><td>{v}/{n}</td><td class={'ok' if v == n else 'bad'}>{100 * v / n:.0f}%</td></tr>"
        for m, v in summary.items()
    )
    html = f"""<!doctype html><meta charset=utf-8><title>AgentKart evals</title>
<style>body{{font:16px system-ui;max-width:720px;margin:40px auto}}td,th{{padding:6px 14px;text-align:left;border-bottom:1px solid #ddd}}
.ok{{color:#059669;font-weight:600}}.bad{{color:#dc2626;font-weight:600}}</style>
<h1>AgentKart deterministic evals</h1><p>{n} generated scenarios through the real pipeline (mock UCP stores, no LLM).
Feasible baskets: {sum(1 for r in rows if r["feasible"])}/{n}.</p>
<table><tr><th>Metric</th><th>Passed</th><th>Rate</th></tr>{cells}</table>"""
    (OUT / "index.html").write_text(html)
    for m, v in summary.items():
        print(f"{m:28s} {v}/{n}  {'PASS' if v == n else 'FAIL'}")
    print("report:", OUT / "index.html")
    if any(v != n for v in summary.values()):
        sys.exit(1)


if __name__ == "__main__":
    report(asyncio.run(run()))
