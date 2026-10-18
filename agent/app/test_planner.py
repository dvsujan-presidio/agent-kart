"""Dynamic planning: the model proposes items and rules; Python validates and does the arithmetic."""

import pytest
from fastapi.testclient import TestClient

from app.approval import ApprovalGate
from app.config import Settings
from app.main import create_app
from app.orchestrator import Orchestrator
from app.planner import ItemSpec, ShoppingPlan, items_for, validate
from app.real_stores.service import load_store_config
from app.real_stores.test_real import CALLS, PROFILE, handler, make_service, tp  # noqa: F401
from app.testing import inproc_clients

IDS = set(load_store_config())
COVERS = {
    sid: {str(c).replace("_", " ") for c in cfg["covers"]}
    for sid, cfg in load_store_config().items()
}


def spec(
    cat,
    query=None,
    kws=None,
    basis="per_person",
    rate=1.0,
    stores=("peachstate",),
    req=True,
    label=None,
):
    return ItemSpec(
        category=cat,
        label=label or cat,
        query=query or cat,
        keywords=kws or [cat],
        avoid=[],
        basis=basis,
        rate=rate,
        required=req,
        stores=list(stores),
        why="",
    )


def test_validate_sanitizes_model_output():
    plan = ShoppingPlan(
        title="t",
        items=[
            spec(
                "Popcorn Tin!", query="popcorn <script>", kws=["Popcorn"], stores=("nope", "dylans")
            ),
            spec("popcorn_tin", stores=("dylans",)),  # duplicate slug
            spec("cups", rate=9999, stores=("ghost",)),  # unknown store, crazy rate
            ItemSpec(
                category="x",
                label="x",
                query="",
                keywords=[],
                avoid=[],
                basis="fixed",
                rate=1,
                required=False,
                stores=["dylans"],
                why="",
            ),  # unusable
        ],
    )
    out = validate(plan, IDS, COVERS)
    assert [o.category for o in out] == ["popcorn_tin", "cups"]
    assert out[0].stores == ["dylans"] and "<" not in out[0].query
    assert out[1].rate <= 12 and out[1].stores  # unknown store replaced by routing on tags


def test_items_for_is_deterministic_arithmetic():
    items = items_for([spec("cups", rate=1.5), spec("stove", basis="fixed", rate=1)], guests=5)
    assert [i.need_qty for i in items] == [8.0, 1.0]  # ceil(1.5*5), fixed 1
    assert items[0].rule == "5 people x 1.5 each = 8" and items[1].rule == "1 for the group"


class ScriptedPlanner:
    def __init__(self, plan, extra=None):
        self._plan, self._extra, self.calls = plan, extra, []

    async def plan(self, goal, guests, menu, extra=None, existing=None):
        self.calls.append({"goal": goal, "guests": guests, "extra": extra, "existing": existing})
        return self._extra if extra else self._plan


def stack(planner, script):
    clients, _ = inproc_clients()
    cfg = Settings(
        approval_hmac_secret="t",
        demo_mode=True,
        agent_profile_url_env=PROFILE,
        real_store_scenarios="camping_weekend,birthday_party",
    )

    class N:
        async def parse(self, history, ctx):
            return script[history[-1]["content"]]

    orch = Orchestrator(
        clients=clients,
        nlu=N(),
        gate=ApprovalGate("t", 90),
        settings=cfg,
        real=make_service(),
        planner=planner,
    )
    return TestClient(create_app(orch, cfg))


MOVIE = ShoppingPlan(
    title="Movie night",
    items=[
        spec("popcorn", query="popcorn", kws=["popcorn"], rate=1, stores=("dylans",)),
        spec("cups", query="paper cups", kws=["cup"], rate=1.5, stores=("peachstate",), req=False),
        spec(
            "blanket",
            query="blanket",
            kws=["blanket"],
            basis="fixed",
            rate=2,
            stores=("rumpl",),
            req=False,
        ),
        spec(
            "unicorn_cape",
            query="unicorn cape",
            kws=["cape"],
            rate=1,
            stores=("peachstate",),
            req=False,
            label="Unicorn cape",
        ),  # no store stocks it
    ],
)


def basket(c, sid):
    return c.get(f"/sessions/{sid}/basket").json()["basket"]


def test_unknown_scenario_is_planned_dynamically_and_sized_in_python():
    planner = ScriptedPlanner(MOVIE)
    script = {
        "go": tp(
            scenario="movie_night",
            goal_summary="movie night for 4 kids",
            guests=4,
            budget_amount=300,
        )
    }
    with stack(planner, script) as c:
        sid = c.post("/sessions").json()["session_id"]
        CALLS.clear()
        c.post(f"/sessions/{sid}/messages", json={"text": "go", "channel": "web"})
        b = basket(c, sid)
        assert b["mode"] == "real" and b["feasible"]
        assert (
            planner.calls[0]["goal"] == "movie night for 4 kids" and planner.calls[0]["guests"] == 4
        )
        lines = {ln["category"]: ln for ln in b["lines"]}
        assert set(lines) == {"popcorn", "cups", "blanket"}  # cape: nobody stocks it
        assert lines["cups"]["rule"] == "4 people x 1.5 each = 6" and lines["blanket"]["packs"] == 2
        assert any("couldn't find in stock: Unicorn cape" in n for n in b["notes"])
        assert {t for _, t in CALLS} == {"search_catalog"}


def test_add_and_remove_items_by_words():
    extra = ShoppingPlan(
        title="x",
        items=[
            spec(
                "lantern",
                query="lantern",
                kws=["lantern", "alpenglow"],
                basis="fixed",
                rate=1,
                stores=("biolite",),
                req=False,
                label="Lantern",
            )
        ],
    )
    planner = ScriptedPlanner(MOVIE, extra)
    script = {
        "go": tp(scenario="movie_night", goal_summary="movie night", guests=4, budget_amount=300),
        "add": tp(intent="edit", add_items=["a lantern"]),
        "drop": tp(intent="edit", drop_categories=["the popcorn"]),
    }
    with stack(planner, script) as c:
        sid = c.post("/sessions").json()["session_id"]
        for t in ("go", "add"):
            c.post(f"/sessions/{sid}/messages", json={"text": t, "channel": "web"})
        assert "lantern" in {ln["category"] for ln in basket(c, sid)["lines"]}
        assert (
            planner.calls[1]["extra"] == ["a lantern"] and "popcorn" in planner.calls[1]["existing"]
        )
        c.post(f"/sessions/{sid}/messages", json={"text": "drop", "channel": "web"})
        assert "popcorn" not in {ln["category"] for ln in basket(c, sid)["lines"]}


def test_planner_failure_on_unknown_job_is_handled_not_crashing():
    class Boom:
        async def plan(self, *a, **k):
            raise RuntimeError("model down")

    script = {
        "go": tp(scenario="movie_night", goal_summary="movie night", guests=4, budget_amount=300)
    }
    with stack(Boom(), script) as c:
        sid = c.post("/sessions").json()["session_id"]
        r = c.post(f"/sessions/{sid}/messages", json={"text": "go", "channel": "web"})
        assert r.status_code == 200 and basket(c, sid) is None
        assert "trouble" in r.json()["reply"].lower() or "couldn't" in r.json()["reply"].lower()


@pytest.mark.parametrize(
    "w,cat", [("cooler", "cooler"), ("coolers", "cooler"), ("the Power Bank", "power_bank")]
)
def test_match_spec_is_forgiving(w, cat):
    from app.orchestrator import match_spec

    assert match_spec([spec("cooler"), spec("power_bank", label="Power bank")], w) == cat
