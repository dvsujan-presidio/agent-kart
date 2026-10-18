"""In-process store clients for tests, evals and offline demos (no sockets)."""

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from app.ucp_client import StoreClient
from stores.server import create_app

DATA = Path(__file__).resolve().parents[2] / "stores" / "data"
IST = ZoneInfo("Asia/Kolkata")


def inproc_clients(sim_fast: bool = True) -> tuple[list[StoreClient], dict]:
    apps, mounts = {}, {}
    for f in sorted(DATA.glob("*.json")):
        sid = f.stem
        app = create_app(f, base_url=f"http://{sid}", sim_fast=sim_fast)
        apps[sid] = app
        mounts[f"http://{sid}"] = httpx.ASGITransport(app=app)
    http = httpx.AsyncClient(mounts=mounts)
    return [StoreClient(f"http://{sid}", http) for sid in apps], apps


def tomorrow_at(hour: int, now: datetime | None = None) -> datetime:
    now = now or datetime.now(IST)
    return (now + timedelta(days=1)).replace(hour=hour, minute=0, second=0, microsecond=0)
