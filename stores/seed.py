"""Generates the four mock store catalogs (INR, paise). Run: python -m stores.seed

Prices are tuned so the demo story works (see docs/demo-script.md).
ETA rules are relative to 'now' in the store timezone: {"days": N, "time": "HH:MM"}.
"""

import json
from pathlib import Path

DATA = Path(__file__).parent / "data"


def p(pid, title, cat, pack, unit, price, eta, rating=4.2, stock=True, **attrs):
    return {
        "product_id": pid,
        "variant_id": pid,
        "title": title,
        "category": cat,
        "pack_size": pack,
        "unit": unit,
        "price_minor": price * 100,
        "rating": rating,
        "in_stock": stock,
        "eta_rule": eta,
        "attributes": attrs,
    }


def cakes():
    out = []
    sizes = {0.5: (850, 1150), 1.0: (1450, 1650), 1.5: (1750, 2050)}
    for flavor in ("chocolate", "vanilla", "butterscotch"):
        for kg, (std, prem) in sizes.items():
            for tier, base in (("standard", std), ("premium", prem)):
                for eggless in (False, True):
                    name = f"{flavor.title()} {'Truffle ' if tier == 'premium' else ''}Cake {kg} kg"
                    if eggless:
                        name += " (eggless)"
                    out.append(
                        p(
                            f"cake-{flavor}-{tier}-{kg}-{'e' if eggless else 'x'}",
                            name,
                            "cake",
                            kg,
                            "kg",
                            base + (50 if eggless else 0),
                            {"days": 0, "time": "17:00"},
                            4.6 if tier == "premium" else 4.3,
                            flavor=flavor,
                            tier=tier,
                            eggless=eggless,
                        )
                    )
    return out


STORES = {
    "cakecorner": {
        "name": "CakeCorner",
        "port": 8201,
        "delivery_fee": 49,
        "free_above": 999,
        "min_order": 0,
        "products": cakes()
        + [
            p(
                "candles-cc",
                "Birthday candles (pack of 12)",
                "candles",
                12,
                "pcs",
                60,
                {"days": 0, "time": "17:00"},
            ),
            p("knife-cc", "Cake knife", "cake_knife", 1, "pcs", 40, {"days": 0, "time": "17:00"}),
        ],
    },
    "snackmart": {
        "name": "SnackMart",
        "port": 8202,
        "delivery_fee": 39,
        "free_above": 500,
        "min_order": 0,
        "products": [
            p(
                "chips-200",
                "Salted potato chips 200 g",
                "snacks",
                200,
                "g",
                95,
                {"days": 1, "time": "11:00"},
            ),
            p(
                "namkeen-400",
                "Mixed namkeen 400 g",
                "snacks",
                400,
                "g",
                180,
                {"days": 1, "time": "11:00"},
            ),
            p(
                "cookies-300",
                "Butter cookies 300 g",
                "snacks",
                300,
                "g",
                130,
                {"days": 1, "time": "11:00"},
            ),
            p("cola-2l", "Cola 2 L", "drinks", 2, "L", 120, {"days": 1, "time": "11:00"}),
            p(
                "juice-2l",
                "Mixed fruit juice 2 L",
                "drinks",
                2,
                "L",
                140,
                {"days": 1, "time": "11:00"},
            ),
            p(
                "cups-10-sm",
                "Paper cups (pack of 10)",
                "cups",
                10,
                "pcs",
                70,
                {"days": 1, "time": "11:00"},
            ),
            p(
                "cups-25-sm",
                "Paper cups (pack of 25)",
                "cups",
                25,
                "pcs",
                150,
                {"days": 1, "time": "11:00"},
            ),
            p(
                "napkins-50-sm",
                "Paper napkins (pack of 50)",
                "napkins",
                50,
                "pcs",
                42,
                {"days": 1, "time": "11:00"},
            ),
            p(
                "plates-10-sm",
                "Paper plates (pack of 10)",
                "plates",
                10,
                "pcs",
                70,
                {"days": 1, "time": "11:00"},
            ),
            p(
                "candles-sm",
                "Birthday candles (pack of 12)",
                "candles",
                12,
                "pcs",
                47,
                {"days": 1, "time": "11:00"},
            ),
            p(
                "balloons-20-sm",
                "Latex balloons (pack of 20)",
                "balloons",
                20,
                "pcs",
                92,
                {"days": 1, "time": "11:00"},
            ),
            p(
                "banner-sm",
                "Happy Birthday banner",
                "banner",
                1,
                "pcs",
                152,
                {"days": 1, "time": "11:00"},
            ),
            p(
                "hats-10-sm",
                "Party hats (pack of 10)",
                "party_hats",
                10,
                "pcs",
                122,
                {"days": 1, "time": "11:00"},
            ),
        ],
    },
    "partybazaar": {
        "name": "PartyBazaar",
        "port": 8203,
        "delivery_fee": 59,
        "free_above": 0,
        "min_order": 0,
        "products": [
            # cheapest cups, but they arrive the day after tomorrow: the 'late item' story
            p(
                "cups-25-pb",
                "Paper cups (pack of 25)",
                "cups",
                25,
                "pcs",
                85,
                {"days": 2, "time": "12:00"},
            ),
            p(
                "plates-10-pb",
                "Paper plates (pack of 10)",
                "plates",
                10,
                "pcs",
                60,
                {"days": 1, "time": "14:00"},
            ),
            p(
                "balloons-20-pb",
                "Latex balloons (pack of 20)",
                "balloons",
                20,
                "pcs",
                90,
                {"days": 1, "time": "14:00"},
            ),
            p(
                "balloons-20-prem",
                "Metallic balloons (pack of 20)",
                "balloons",
                20,
                "pcs",
                160,
                {"days": 1, "time": "14:00"},
            ),
            p(
                "banner-pb",
                "Happy Birthday banner",
                "banner",
                1,
                "pcs",
                150,
                {"days": 1, "time": "14:00"},
            ),
            p(
                "hats-10-pb",
                "Party hats (pack of 10)",
                "party_hats",
                10,
                "pcs",
                120,
                {"days": 1, "time": "14:00"},
            ),
            p(
                "candles-pb",
                "Birthday candles (pack of 12)",
                "candles",
                12,
                "pcs",
                45,
                {"days": 1, "time": "14:00"},
            ),
            p(
                "napkins-50-pb",
                "Paper napkins (pack of 50)",
                "napkins",
                50,
                "pcs",
                40,
                {"days": 1, "time": "14:00"},
            ),
        ],
    },
    "nearbybakery": {
        "name": "NearbyBakery (pickup)",
        "port": 8204,
        "delivery_fee": 0,
        "free_above": 0,
        "min_order": 0,
        "pickup_only": True,
        "products": [
            p(
                f"nb-cake-{f}-1.5",
                f"{f.title()} Cake 1.5 kg",
                "cake",
                1.5,
                "kg",
                1780,
                {"hours": 1},
                4.4,
                flavor=f,
                tier="standard",
                eggless=False,
            )
            for f in ("chocolate", "vanilla")
        ]
        + [
            p(
                "nb-cake-chocolate-1.5-e",
                "Chocolate Cake 1.5 kg eggless",
                "cake",
                1.5,
                "kg",
                1830,
                {"hours": 1},
                4.4,
                flavor="chocolate",
                tier="standard",
                eggless=True,
            ),
        ],
    },
}


def main() -> None:
    DATA.mkdir(exist_ok=True)
    for sid, cfg in STORES.items():
        (DATA / f"{sid}.json").write_text(json.dumps({"id": sid, **cfg}, indent=1))
        print(sid, len(cfg["products"]), "products")


if __name__ == "__main__":
    main()
