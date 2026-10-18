"""Real Store Mode tests with a fake UCP/MCP transport: no live network."""

import httpx
import pytest
from fastapi.testclient import TestClient

from app.approval import ApprovalGate
from app.config import Settings
from app.main import create_app
from app.nlu import TurnParse
from app.orchestrator import Orchestrator
from app.real_stores.mcp_client import ALLOWED_TOOLS, McpError, McpStore
from app.real_stores.service import RealStoreService, offers_from_products, parse_pack_size
from app.testing import inproc_clients

PROFILE = "https://profile.example/agent.json"
CALLS: list[tuple[str, str]] = []


def variant(vid, price, avail=True, title="Default Title"):
    return {
        "id": vid,
        "title": title,
        "price": {"amount": price, "currency": "USD"},
        "availability": {"available": avail},
        "media": [{"url": "https://img/x.png"}],
    }


CATALOG = {
    "headlamp": [
        {
            "id": "p1",
            "title": "Trail Headlamp 200",
            "url": "https://s/p1",
            "variants": [variant("v1a", 3500, False), variant("v1b", 4000), variant("v1c", 4500)],
        },
        {"id": "p2", "title": "Teca Fleece Headband", "variants": [variant("v2", 2000)]},
    ],
    "camp mug": [{"id": "p3", "title": "Camp Mug 12 OZ", "variants": [variant("v3", 2500)]}],
    "blanket": [{"id": "p4", "title": "Puffy Blanket", "variants": [variant("v4", 10000)]}],
    "camp stove": [{"id": "p5", "title": "CampStove", "variants": [variant("v5", 20000)]}],
    "lantern": [{"id": "p6", "title": "AlpenGlow 250", "variants": [variant("v6", 7000)]}],
    "cooler": [{"id": "p7", "title": "Easy Cooler 16 QT", "variants": [variant("v7", 8000)]}],
    "popcorn": [{"id": "pp", "title": "Gourmet Popcorn Tin", "variants": [variant("v9", 1500)]}],
    "paper cups": [
        {"id": "pc", "title": "Solid Paper Cups 8ct", "variants": [variant("v10", 600)]}
    ],
    "power bank charger": [
        {"id": "p8", "title": "Charge 40 PD", "variants": [variant("v8", 6995)]}
    ],
}


def handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/.well-known/ucp":
        host = request.url.host
        return httpx.Response(
            200,
            json={
                "ucp": {
                    "version": "2026-08-25",
                    "services": {
                        "dev.ucp.shopping": [
                            {
                                "version": "2026-08-25",
                                "transport": "mcp",
                                "endpoint": f"https://{host}/api/ucp/mcp",
                            }
                        ]
                    },
                    "capabilities": {
                        "dev.ucp.shopping.catalog.search": [{}],
                        "dev.ucp.shopping.cart": [{}],
                    },
                }
            },
        )
    body = request.read().decode()
    import json

    rpc = json.loads(body)
    p = rpc["params"]
    CALLS.append((request.url.host, p["name"]))
    assert p["arguments"]["meta"]["ucp-agent"]["profile"] == PROFILE  # every call identifies us
    if p["name"] == "search_catalog":
        q = p["arguments"]["catalog"]["query"]
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"structuredContent": {"products": CATALOG.get(q, [])}},
            },
        )
    if p["name"] == "create_cart":
        lines = p["arguments"]["cart"]["line_items"]
        price = {
            "v1b": 4000,
            "v3": 2500,
            "v4": 10000,
            "v5": 20000,
            "v6": 7000,
            "v7": 8000,
            "v8": 6995,
        }
        sub = sum(price[ln["item"]["id"]] * ln["quantity"] for ln in lines)
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "structuredContent": {
                        "id": "cart1",
                        "currency": "USD",
                        "totals": [{"type": "subtotal", "amount": sub}],
                        "continue_url": f"https://{request.url.host}/cart/c/abc",
                    }
                },
            },
        )
    raise AssertionError(f"unexpected tool {p['name']}")


def make_service(**cfg_kw) -> RealStoreService:
    cfg = Settings(
        agent_profile_url_env=PROFILE,
        real_store_scenarios="camping_weekend,birthday_party",
        **cfg_kw,
    )
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    svc = RealStoreService(cfg, http)
    for st in svc.stores.values():  # same stores, fake transport
        st.http = http
    return svc


@pytest.mark.parametrize(
    "title,n",
    [
        ("Paper Cups (8ct)", 8),
        ("Classic Soda Variety Pack (12 Cans)", 12),
        ("OLIPOP 12 Pack", 12),
        ("Set of 2 towels", 2),
        ("Cookware Set", 1),
        ("Napkins 20-ct", 20),
        ("Great Tee", 1),
    ],
)
def test_parse_pack_size(title, n):
    assert parse_pack_size(title) == n


def test_offers_keep_on_topic_cheapest_available_variant():
    svc = make_service()
    offers = offers_from_products(
        svc.stores["biolite"], "headlamp", CATALOG["headlamp"], ["headlamp"]
    )
    assert [o.title for o in offers] == ["Trail Headlamp 200"]  # headband dropped (off topic)
    assert (
        offers[0].price_minor == 4000 and offers[0].variant_id == "v1b"
    )  # out-of-stock 3500 skipped
    assert offers[0].currency == "USD" and offers[0].source == "ucp_real" and offers[0].eta is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool", ["complete_checkout", "create_checkout", "update_checkout", "cancel_checkout"]
)
async def test_checkout_tools_are_refused_before_any_network(tool):
    CALLS.clear()
    st = make_service().stores["biolite"]
    with pytest.raises(McpError) as e:
        await st.call_tool(tool, {})
    assert e.value.code == "forbidden_tool" and CALLS == []
    assert not any("checkout" in t for t in ALLOWED_TOOLS)


@pytest.mark.asyncio
async def test_endpoint_comes_from_manifest_and_profile_is_required():
    st = make_service().stores["biolite"]
    await st.discover()
    assert st.endpoint == "https://bioliteenergy.com/api/ucp/mcp" and st.supports("cart")
    st2 = McpStore("x", "x.com", st.http, lambda: None)
    with pytest.raises(McpError, match="AGENT_PROFILE_URL"):
        await st2.call_tool("search_catalog", {"catalog": {"query": "a"}})


def scripted_nlu(script):
    class N:
        async def parse(self, history, ctx):
            return script[history[-1]["content"]]

    return N()


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


def stack(script):
    clients, _ = inproc_clients()
    cfg = Settings(
        approval_hmac_secret="t",
        demo_mode=True,
        agent_profile_url_env=PROFILE,
        real_store_scenarios="camping_weekend,birthday_party",
    )
    orch = Orchestrator(
        clients=clients,
        nlu=scripted_nlu(script),
        gate=ApprovalGate("t", 90),
        settings=cfg,
        real=make_service(),
    )
    return TestClient(create_app(orch, cfg))


def test_camping_builds_real_basket_then_carts_only_never_orders():
    c = stack(
        {
            "plan": tp(scenario="camping_weekend", guests=4, budget_amount=1500),
            "cart": tp(intent="place_order"),
        }
    ).__enter__()
    sid = c.post("/sessions").json()["session_id"]
    CALLS.clear()
    r = c.post(f"/sessions/{sid}/messages", json={"text": "plan", "channel": "web"}).json()
    b = c.get(f"/sessions/{sid}/basket").json()["basket"]
    assert (
        b["mode"] == "real" and b["currency"] == "USD" and b["estimate"] is True and b["feasible"]
    )
    assert b["total_minor"] == 4 * 4000 + 4 * 2500 + 4 * 10000 + 20000 + 7000 + 8000 + 6995
    assert r["approval_request"] is None
    assert {t for _, t in CALLS} == {"search_catalog"}  # planning only searches, no cart yet
    r = c.post(f"/sessions/{sid}/messages", json={"text": "cart", "channel": "web"}).json()
    assert r["approval_request"] is None and "added everything to carts" in r["reply"]
    assert "create_cart" in {t for _, t in CALLS} and not any("checkout" in t for _, t in CALLS)
    carts = c.get(f"/sessions/{sid}/real/carts").json()["carts"]
    assert carts and all(
        k["handoff_url"].startswith("https://") and k["degraded"] == [] for k in carts
    )
    # the agent has no way to buy on real stores
    assert c.post(f"/sessions/{sid}/approval-request").status_code == 409
    assert c.post(f"/sessions/{sid}/checkout", json={"token": None}).status_code in (403, 409)


def test_cart_failure_degrades_gracefully():
    svc = make_service()

    async def boom(lines):
        raise McpError("x", "store down")

    for st in svc.stores.values():
        st.create_cart = boom
    import asyncio

    from app.pipeline import PlanState
    from app.real_stores.service import build_plan_real

    st = PlanState(
        scenario="camping_weekend",
        currency="USD",
        needs_deadline=False,
        guests=2,
        budget_minor=10**6,
    )
    pr = asyncio.run(build_plan_real(st, svc))
    carts = asyncio.run(svc.build_carts(pr.basket))
    assert carts and all(
        "cart_failed_showing_search_prices" in k.degraded and k.handoff_url is None for k in carts
    )


def test_new_address_is_collected_conversationally_and_used_in_readback():
    script = {
        "plan": tp(
            scenario="birthday_party",
            guests=10,
            budget_amount=3000,
            deadline_iso=__import__("app.testing", fromlist=["x"]).tomorrow_at(18).isoformat(),
        ),
        "chocolate": tp(cake_flavor="chocolate"),
        "no egg": tp(eggless=False),
        "other address": tp(use_saved_address=False),
        "street": tp(address_text="45 MG Road", address_area="Camp"),
        "pin": tp(address_pincode="411 001"),
        "city": tp(address_city="Pune"),
        "place": tp(intent="place_order"),
    }
    c = stack(script).__enter__()
    sid = c.post("/sessions").json()["session_id"]

    def say(t):
        return c.post(f"/sessions/{sid}/messages", json={"text": t, "channel": "web"}).json()

    say("plan")
    say("chocolate")
    r = say("no egg")
    assert "saved address" in r["reply"]
    assert "address" in say("other address")["reply"].lower()  # asks for the new address
    assert "pincode" in say("street")["reply"].lower()  # then the pincode
    assert "city" in say("pin")["reply"].lower()  # then the city
    say("city")
    b = c.get(f"/sessions/{sid}/basket").json()["basket"]
    assert b["address"] == "45 MG Road, Camp, Pune 411001"
    rb = say("place")["approval_request"]["readback"]
    assert "Camp, Pune" in rb


def test_seasonal_and_character_items_are_skipped():
    svc = make_service()
    prods = [
        {"id": "a", "title": "Cocomelon Party Hats 8ct", "variants": [variant("va", 400)]},
        {"id": "b", "title": "Holiday Snowflake Napkins", "variants": [variant("vb", 300)]},
        {"id": "c", "title": "Solid Gold Party Hats 10ct", "variants": [variant("vc", 500)]},
    ]
    offers = offers_from_products(svc.stores["peachstate"], "party_hats", prods, ["hat", "napkin"])
    assert [o.title for o in offers] == ["Solid Gold Party Hats 10ct"] and offers[0].pack_size == 10


def test_pack_size_comes_from_variant_title_too():
    svc = make_service()
    prods = [
        {
            "id": "o",
            "title": "Classic Soda Variety Pack",
            "variants": [variant("vo", 3599, title="12 Cans")],
        }
    ]
    o = offers_from_products(svc.stores["olipop"], "drinks", prods, ["pack"])[0]
    assert o.pack_size == 12 and o.title.endswith("(12 Cans)")
