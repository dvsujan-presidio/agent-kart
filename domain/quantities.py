"""Quantity rules and pack rounding. Exact arithmetic (Fraction); no floats in results."""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import yaml

from contracts.models import ListItem

TEMPLATE_DIR = Path(__file__).parent / "templates"

# Everything is stored in base units so offers in kg / L compare with needs in g / ml.
_TO_BASE = {"kg": ("g", 1000), "g": ("g", 1), "l": ("ml", 1000), "ml": ("ml", 1), "pcs": ("pcs", 1)}


def to_base(qty: float | Fraction, unit: str) -> tuple[Fraction, str]:
    base, factor = _TO_BASE[unit.lower()]
    return Fraction(str(qty)) * factor, base


def _fmt(q: Fraction) -> str:
    return str(int(q)) if q.denominator == 1 else str(float(q))


@dataclass(frozen=True)
class TemplateItem:
    category: str
    unit: str
    basis: str  # per_guest | fixed | per_pref
    rate: Fraction
    required: bool
    aliases: tuple[str, ...]
    min: Fraction = Fraction(0)
    pref: str | None = None


def list_scenarios() -> list[str]:
    return sorted(p.stem for p in TEMPLATE_DIR.glob("*.yaml"))


def load_template(scenario: str) -> list[TemplateItem]:
    path = TEMPLATE_DIR / f"{scenario}.yaml"
    if not path.exists():
        raise KeyError(f"unknown scenario {scenario!r}")
    raw = yaml.safe_load(path.read_text())
    return [
        TemplateItem(
            category=i["category"],
            unit=i["unit"],
            basis=i["basis"],
            rate=Fraction(str(i["rate"])),
            required=i.get("required", True),
            aliases=tuple(a.lower() for a in i.get("aliases", [i["category"]])),
            min=Fraction(str(i.get("min", 0))),
            pref=i.get("pref"),
        )
        for i in raw["items"]
    ]


def is_excluded(item: TemplateItem, exclusions: list[str]) -> bool:
    ex = {e.strip().lower() for e in exclusions}
    return item.category in ex or any(a in ex for a in item.aliases)


def plan_list(
    scenario: str, guests: int, exclusions: list[str] | None = None, preferences: dict | None = None
) -> list[ListItem]:
    """Shopping list for a goal. Quantities come only from here, never from an LLM."""
    if guests < 1:
        raise ValueError("guests must be >= 1")
    prefs = preferences or {}
    out: list[ListItem] = []
    for t in load_template(scenario):
        if is_excluded(t, exclusions or []):
            continue
        if t.basis == "per_guest":
            count, how = Fraction(guests), f"{guests} guests x {_fmt(t.rate)} {t.unit}"
            need = max(t.rate * guests, t.min)
        elif t.basis == "per_pref":
            n = int(prefs.get(t.pref or "", 1))
            need = max(t.rate * n, t.min)
            how = f"{n} {t.pref} x {_fmt(t.rate)} {t.unit}"
            count = Fraction(n)
        else:  # fixed
            need, how, count = max(t.rate, t.min), f"{_fmt(t.rate)} {t.unit} per order", Fraction(1)
        need = Fraction(math.ceil(need))
        rule = f"{how} = {_fmt(t.rate * count)} {t.unit}"
        if need != t.rate * count:
            rule += f", minimum {_fmt(need)} {t.unit}"
        out.append(
            ListItem(
                category=t.category,
                need_qty=float(need),
                unit=t.unit,
                rule=rule,
                required=t.required,
            )
        )
    return out


def packs_needed(need_qty: float, need_unit: str, pack_size: float, pack_unit: str) -> int | None:
    """Fewest packs covering the need; None when the units are not comparable."""
    need, nb = to_base(need_qty, need_unit)
    pack, pb = to_base(pack_size, pack_unit)
    if nb != pb or pack <= 0:
        return None
    return max(1, math.ceil(need / pack))
