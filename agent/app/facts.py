"""Builds the (goal, facts, placeholders) brief for the conversation layer from session state.

All numbers live in `placeholders` (already formatted for the channel); `descriptions` tells the
model what each placeholder means without revealing its value, so it cannot copy digits.
"""

from __future__ import annotations

from app import narrate
from app.session import Session
from voice.speech_format import speak_time

HINT = {
    "guests": "how many people it is for",
    "budget": "their budget",
    "deadline": "when they need everything by",
    "cake_flavor": "which cake flavor they'd like",
    "eggless": "whether the cake should be eggless",
    "address": "whether to deliver to their saved address (the area name is in facts.saved_area)",
    "address_new": "the new delivery address they want (street or house, area, city, pincode); just ask for it",
    "address_pincode": "the pincode of the new delivery address (one question)",
    "address_city": "which city the new delivery address is in (one question)",
}


def _day(dt, now) -> str:
    return speak_time(dt, now).split(" ", 2)[-1]


def build(orch, s: Session, situation: str) -> tuple[str, dict, dict, dict]:
    """Returns (goal, facts, placeholders, descriptions)."""
    st, ch, now = s.state, s.channel, orch.clock()
    ph: dict[str, str] = {}
    desc: dict[str, str] = {}
    facts: dict = {"channel": ch}

    def add(name: str, value: str, meaning: str) -> None:
        ph[name], desc[name] = value, meaning

    known = {}
    if st.guests:
        known["people"] = "known"
        add("guests", str(st.guests), "number of people")
    if st.budget_minor:
        add("budget", narrate.say_money(st.budget_minor, st.currency, ch), "their budget")
    if st.deadline:
        add("deadline", speak_time(st.deadline, now), "when they need it by")
    facts["already_known"] = {
        "occasion": st.scenario.replace("_", " "),
        "people": bool(st.guests),
        "budget": bool(st.budget_minor),
        "deadline": bool(st.deadline),
        "already_have": sorted(st.exclusions),
        "cake_flavor": st.prefs.get("cake_flavor"),
        "eggless": st.prefs.get("eggless"),
        "saved_area": orch._address_label(s),
    }

    facts["store_mode"] = (
        "real US stores in dollars: carts only, the shopper pays on each store's own "
        "site, nothing is ordered by you"
        if st.currency == "USD"
        else "demo stores in rupees: you can place the order after the shopper approves"
    )
    if s.real_carts:
        facts["real_carts"] = [
            {"store": narrate.store_label(c.store_id), "has_link": bool(c.handoff_url)}
            for c in s.real_carts
        ]
    plan = s.plan
    if plan is not None and plan.basket.lines:
        b = plan.basket
        left = b.budget_minor - b.total_minor
        add(
            "total",
            narrate.say_money(b.total_minor, b.currency, ch),
            "basket total including delivery",
        )
        add("budget", narrate.say_money(b.budget_minor, b.currency, ch), "their budget")
        add("stores", str(narrate.n_stores(b)), "number of stores used")
        add("items", str(len(b.lines)), "number of items")
        facts["within_budget"] = left >= 0
        if left >= 0:
            add("left", narrate.say_money(left, b.currency, ch), "amount still left under budget")
        else:
            add("over", narrate.say_money(-left, b.currency, ch), "amount over budget")
        if (
            plan.insight
            and plan.insight.saving_minor > 0
            and plan.insight.optimal_stores < plan.insight.naive_stores
        ):
            add(
                "saving",
                narrate.say_money(plan.insight.saving_minor, b.currency, ch),
                "money saved by using fewer stores (delivery fees)",
            )
            add(
                "optimal_stores",
                str(plan.insight.optimal_stores),
                "stores used after consolidating",
            )
            add(
                "naive_stores",
                str(plan.insight.naive_stores),
                "stores that would have been needed otherwise",
            )
            facts["saving_from_fewer_stores"] = True
        if plan.late_notes:
            n = plan.late_notes[0]
            add(
                "late_saving",
                narrate.say_money(n.cheaper_by_minor, b.currency, ch),
                "how much cheaper the late offer was",
            )
            add("late_day", _day(n.eta, now), "when the too-late offer would arrive")
            facts["late_offer_excluded"] = {
                "store": narrate.store_label(n.store_id),
                "item": n.category.replace("_", " "),
            }
        if plan.notes:
            facts["notes"] = plan.notes
        if b.total_is_estimate:
            facts["total_is_estimate"] = True
        facts["items_in_basket"] = [
            {
                "item": ln.offer.category.replace("_", " "),
                "title": ln.offer.title,
                "packs": ln.packs,
                "rule_used": next(
                    (i.rule for i in plan.items if i.category == ln.offer.category), ""
                ),
            }
            for ln in b.lines
        ]
        if plan.options:
            facts["options"] = []
            for i, o in enumerate(plan.options, 1):
                add(f"opt{i}_title", o.tradeoff.title.lower(), f"option {i}: what changes")
                add(
                    f"opt{i}_saving",
                    narrate.say_money(-o.tradeoff.delta_minor, b.currency, ch),
                    f"option {i}: money saved",
                )
                add(
                    f"opt{i}_total",
                    narrate.say_money(o.tradeoff.basket.total_minor, b.currency, ch),
                    f"option {i}: new total",
                )
                facts["options"].append(
                    {
                        "n": i,
                        "title": f"{{opt{i}_title}}",
                        "saves": f"{{opt{i}_saving}}",
                        "new_total": f"{{opt{i}_total}}",
                        "within_budget": o.tradeoff.basket.total_minor <= st.budget_minor,
                    }
                )
        if st.payers > 1:
            from domain.split import split_equal

            shares = split_equal(b.total_minor, st.payers)
            add("payers", str(st.payers), "number of people splitting")
            add(
                "share_hi",
                narrate.say_money(max(shares), b.currency, ch),
                "largest share per person",
            )
            add(
                "share_lo",
                narrate.say_money(min(shares), b.currency, ch),
                "smallest share per person",
            )
            facts["shares_all_equal"] = len(set(shares)) == 1

    goals = {
        "greet": "Greet them warmly in your own words, say in one line what you can do (plan, budget and "
        "order a whole job such as a birthday party across stores), and ask what they're planning.",
        "plan_ready": "Tell them the plan is ready: the {total} total across {stores} stores and how much is "
        "left or over their budget. If saving_from_fewer_stores, mention {saving} saved by "
        "using fewer stores. If late_offer_excluded, mention that cheaper-but-late offer was "
        "skipped because it would arrive {late_day}. Mention anything they said they already "
        "have that you left out. Then invite tweaks or say they can tell you to place the order.",
        "over_budget": "Tell them it comes to {total}, {over} over their {budget} budget. If voice, offer ONLY "
        "option 1 (what it changes and what it saves) and say the others are on screen; if chat, "
        "briefly present all options. Ask which they'd like.",
        "option_applied": "Confirm you applied the change they chose, then give the updated plan: {total}, "
        "and how it sits against budget. Invite tweaks or placing the order.",
        "plan_summary": "They asked about the plan. Answer their question using only the facts "
        "(items_in_basket, rules). Keep the totals via placeholders. Offer to change something.",
        "split": "Tell them the split: with {payers} people each pays {share_hi} (if not shares_all_equal, "
        "some pay {share_lo}). Offer anything else.",
        "nothing_to_order": "Explain nothing can be ordered yet because you don't have a plan, and ask what "
        "they're planning.",
        "cannot_place": "Explain you can't place it yet because it's over budget or something is missing, and "
        "nudge them toward the options.",
        "already_ordered": "Tell them that order is already placed and they can follow it in the tracker.",
        "unsupported": "Say honestly that right now you can only plan birthday parties from the demo stores; "
        "other jobs need Real Store Mode which isn't enabled in this build. Offer a birthday plan.",
        "clarify_option": "Ask which option number they'd like.",
        "no_options": "Say there are no options to apply right now.",
        "real_handoff": "Tell them you've added everything to carts at the real stores (store names are in "
        "facts.real_carts), that you have NOT ordered or paid for anything, prices are estimates "
        "with shipping and tax added at each store's checkout, and that they can open each cart "
        "from the buttons on screen to review and pay there themselves.",
        "real_unavailable": "Explain that to use real stores the agent's public profile has to be online "
        "first and that it isn't right now; offer the demo stores meanwhile.",
    }
    if situation.startswith("ask:"):
        key = situation.split(":", 1)[1]
        facts["ask_for"] = HINT[key]
        if key == "address":
            facts["saved_area"] = orch._address_label(s)
        goal = (
            "Acknowledge what they just said in a few words, then ask for "
            + HINT[key]
            + ". One natural question, no list."
        )
    else:
        goal = goals.get(situation, "Reply helpfully and briefly.")
    return goal, facts, ph, desc
