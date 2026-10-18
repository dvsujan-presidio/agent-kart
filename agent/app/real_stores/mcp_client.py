"""UCP-over-MCP client for real stores.

Rules: endpoints come from each store's /.well-known/ucp manifest at runtime (never
hardcoded), every call carries AgentKart's agent profile URL, 429/Retry-After is honoured, concurrency
is limited per store, nothing here ever sends payment details or completes a purchase, no scraping.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from pathlib import Path

import httpx

RECORDINGS = Path(__file__).parent / "recordings"
PROTOCOL = "2025-06-18"
SHOPPING = "dev.ucp.shopping"


# Real stores are read-and-cart only. Anything that could place an order or take payment is refused
# here, in code, regardless of what any caller or model asks for.
ALLOWED_TOOLS = frozenset(
    {"search_catalog", "lookup_catalog", "get_product", "create_cart", "get_cart", "update_cart"}
)


class McpError(Exception):
    def __init__(self, code: int | str, message: str, data=None):
        super().__init__(f"{code}: {message} {data if data else ''}".strip())
        self.code, self.data = code, data


class ReplayMiss(McpError):
    pass


class McpStore:
    def __init__(
        self,
        store_id: str,
        domain: str,
        http: httpx.AsyncClient,
        profile_url,
        *,
        replay: bool = False,
        record: bool = False,
        timeout: float = 20.0,
    ):
        self.store_id, self.domain, self.http = store_id, domain, http
        self._profile_url = profile_url  # callable -> str | None (read per call: tunnels change)
        self.replay, self.record, self.timeout = replay, record, timeout
        self.endpoint: str | None = None
        self.capabilities: set[str] = set()
        self.manifest: dict | None = None
        self._sem = asyncio.Semaphore(2)  # per-store concurrency limit
        self._cache: dict[str, tuple[float, dict]] = {}

    # ---------------------------------------------------------------- discovery
    async def discover(self) -> None:
        if self.endpoint:
            return
        bare = self.domain.removeprefix("www.")
        errors = []
        for host in dict.fromkeys([bare, f"www.{bare}"]):  # apex first, then www
            try:
                if self.replay:
                    self.manifest = self._read("manifest:" + host)
                else:
                    r = await self.http.get(f"https://{host}/.well-known/ucp", timeout=self.timeout)
                    r.raise_for_status()
                    self.manifest = r.json()
                    if self.record:
                        self._write("manifest:" + host, self.manifest)
                break
            except Exception as e:
                errors.append(f"{host}: {e}")
        else:
            raise McpError(
                "discovery_failed", f"{self.store_id}: no UCP manifest ({'; '.join(errors)})"
            )
        ucp = self.manifest.get("ucp", {})
        svc = ucp.get("services", {}).get(SHOPPING, [])
        svc = svc if isinstance(svc, list) else [svc]
        mcp = sorted(
            (x for x in svc if x.get("transport") == "mcp" and x.get("endpoint")),
            key=lambda x: x.get("version", ""),
            reverse=True,
        )
        if not mcp:
            raise McpError("no_mcp", f"{self.store_id} declares no MCP endpoint for {SHOPPING}")
        self.endpoint = mcp[0]["endpoint"]  # read from the manifest, never hardcoded
        caps = ucp.get("capabilities", {})
        self.capabilities = (
            set(caps) if isinstance(caps, dict) else {c.get("name", "") for c in caps}
        )

    def supports(self, capability: str) -> bool:
        return f"{SHOPPING}.{capability}" in self.capabilities

    # --------------------------------------------------------------- transport
    async def _rpc(self, method: str, params: dict) -> dict:
        assert self.endpoint
        body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": f"AgentKart/0.1 (+{self._profile_url() or 'no-profile'})",
        }
        async with self._sem:
            for attempt in range(2):
                r = await self.http.post(
                    self.endpoint, json=body, headers=headers, timeout=self.timeout
                )
                if r.status_code == 429 or r.status_code >= 500:
                    if attempt == 0:
                        await asyncio.sleep(min(float(r.headers.get("Retry-After", "1") or 1), 5))
                        continue
                if r.status_code == 422 or r.status_code == 200:
                    break
                r.raise_for_status()
            try:
                data = r.json()
            except Exception as e:
                raise McpError(
                    "bad_response", f"{self.store_id}: non-JSON reply ({r.status_code})"
                ) from e
        if "error" in data:
            e = data["error"]
            raise McpError(e.get("code"), e.get("message", ""), e.get("data"))
        return data["result"]

    def _key(self, tool: str, args: dict) -> str:
        clean = json.dumps({k: v for k, v in args.items() if k != "meta"}, sort_keys=True)
        return hashlib.sha1(f"{self.store_id}|{tool}|{clean}".encode()).hexdigest()[:16]

    def _read(self, key: str) -> dict:
        p = RECORDINGS / f"{self.store_id}-{hashlib.sha1(key.encode()).hexdigest()[:16]}.json"
        if not p.exists():
            raise ReplayMiss("replay_miss", f"no recording for {self.store_id} {key[:40]}")
        return json.loads(p.read_text())

    def _write(self, key: str, data: dict) -> None:
        RECORDINGS.mkdir(exist_ok=True)
        (
            RECORDINGS / f"{self.store_id}-{hashlib.sha1(key.encode()).hexdigest()[:16]}.json"
        ).write_text(json.dumps(data))

    async def call_tool(self, name: str, arguments: dict) -> dict:
        if name not in ALLOWED_TOOLS:
            raise McpError("forbidden_tool", f"{name} is not allowed on real stores (carts only)")
        key = "tool:" + self._key(name, arguments)
        if self.replay:
            return self._read(key)
        await self.discover()
        profile = self._profile_url()
        if not profile:
            raise McpError(
                "no_profile", "AGENT_PROFILE_URL is not set (see scripts/start_profile.sh)"
            )
        args = {"meta": {"ucp-agent": {"profile": profile}}, **arguments}
        result = await self._rpc("tools/call", {"name": name, "arguments": args})
        sc = result.get("structuredContent")
        if sc is None:
            for c in result.get("content", []):
                if c.get("type") == "text":
                    try:
                        sc = json.loads(c["text"])
                        break
                    except Exception:
                        continue
        if result.get("isError") or sc is None:
            raise McpError("tool_error", f"{self.store_id}.{name} failed", result.get("content"))
        if self.record:
            self._write(key, sc)
        return sc

    # ------------------------------------------------------------------- tools
    async def search(self, query: str, limit: int = 5) -> list[dict]:
        k = f"{query}|{limit}"
        hit = self._cache.get(k)
        if hit and time.time() - hit[0] < 600:
            return hit[1]["products"]
        out = await self.call_tool(
            "search_catalog",
            {
                "catalog": {
                    "query": query,
                    "context": {"address_country": "US", "currency": "USD"},
                    "pagination": {"limit": limit},
                }
            },
        )
        self._cache[k] = (time.time(), out)
        return out.get("products", [])

    async def create_cart(self, lines: list[dict]) -> dict:
        """lines: [{"variant_id": gid, "quantity": n}]. Creates a cart only; never a checkout."""
        return await self.call_tool(
            "create_cart",
            {
                "cart": {
                    "line_items": [
                        {"item": {"id": ln["variant_id"]}, "quantity": ln["quantity"]}
                        for ln in lines
                    ],
                    "context": {"address_country": "US", "currency": "USD"},
                }
            },
        )
