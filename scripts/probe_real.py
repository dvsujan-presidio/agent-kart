"""Live probe: what does each category return from the real stores? (uses live network)
PYTHONPATH=.:agent uv run python scripts/probe_real.py [scenario]
"""

import asyncio
import sys

import httpx
from app.config import get_settings
from app.real_stores.service import RealStoreService, offers_from_products

only = sys.argv[1] if len(sys.argv) > 1 else None


async def main():
    cfg = get_settings()
    async with httpx.AsyncClient(follow_redirects=False) as http:
        svc = RealStoreService(cfg, http)
        print("profile:", svc.profile_url())
        for sc, cats in svc.queries.items():
            if only and sc != only:
                continue
            print(f"\n## {sc}")
            for cat, q in cats.items():
                for sid in q["stores"]:
                    st = svc.stores[sid]
                    try:
                        prods = await st.search(q["query"])
                        offs = offers_from_products(st, cat, prods, q["keywords"])
                        top = (
                            "; ".join(
                                f"{o.title[:42]} ${o.price_minor / 100:.0f}" for o in offs[:3]
                            )
                            or f"(no keyword match among {[p['title'][:25] for p in prods[:3]]})"
                        )
                        print(f"  {cat:12s} {sid:10s} {len(prods)} results -> {top}")
                    except Exception as e:
                        print(f"  {cat:12s} {sid:10s} ERROR {str(e)[:110]}")


asyncio.run(main())
