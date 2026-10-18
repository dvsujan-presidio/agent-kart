"""Conversation layer: an LLM phrases each reply, Python supplies every number.

The model is given a situation + facts + the NAMES of placeholders it may use ({total}, {left}, ...).
It must not write digits, prices or counts itself; Python substitutes placeholder values afterwards.
Anything that breaks the rules (digits, unknown placeholder, markdown, too long, error) falls back to
the deterministic text, so a wrong number can never reach the user.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Protocol

from app.llm import deployment, get_client

PERSONA = """You are AgentKart: a warm, quick, practical shopping assistant who helps people get a whole
job done (a party, a trip, a move) by planning it, budgeting it and ordering it across stores.
You talk like a helpful friend in natural Indian English. You are speaking to someone, so:
- 1 to 3 short sentences. No lists, no markdown, no emoji, no headings.
- Briefly acknowledge what the person just said before asking or informing. Don't parrot it back.
- Ask at most one question at a time, and make it sound natural, not like a form field.
- Vary your wording; never reuse a sentence you already used in this conversation.
- If they greet you or chat, answer like a person would and gently steer to what they want done.

HARD RULES about numbers (the app fills them in for you):
- NEVER write any digit, price, amount, count, date or time yourself, and never spell them out
  (no "two", "hundred", "thousand", "rupees", "tomorrow at five").
- Whenever you need one, write its placeholder in curly braces exactly as listed, e.g. {total}.
  A money placeholder already includes the currency, so do not add "rupees" or the rupee sign.
- Use only the placeholders listed for this situation. Use only the facts given; never invent
  products, prices, stores, delivery promises or discounts.
- Never claim an order is placed unless the facts say so. Never ask for payment details."""

log = logging.getLogger("agentkart.converse")
_PLACEHOLDER = re.compile(r"\{([a-z0-9_]+)\}")
_NUMBER_WORDS = re.compile(r"\b(hundred|thousand|lakh|crore|rupees?|paise)\b", re.I)
_MARKDOWN = re.compile(r"[*`#]|^\s*[-•]\s", re.M)  # underscores are legal inside {placeholders}


class Converser(Protocol):
    async def phrase(
        self,
        *,
        history: list[dict],
        situation: str,
        goal: str,
        facts: dict,
        placeholders: dict[str, str],
        descriptions: dict[str, str],
        channel: str,
    ) -> str | None: ...


class NullConverser:
    """Always defers to the deterministic text (used in tests and when the model is unavailable)."""

    async def phrase(self, **_) -> str | None:
        return None


def render(text: str, placeholders: dict[str, str]) -> str | None:
    """Validate an LLM draft and substitute placeholders; None if it breaks any rule."""
    t = text.strip().strip('"')
    if not t or _MARKDOWN.search(t):
        t = re.sub(_MARKDOWN, "", t).strip()
        if not t:
            return None
    names = _PLACEHOLDER.findall(t)
    if any(n not in placeholders for n in names):
        return None
    bare = _PLACEHOLDER.sub("", t)
    if re.search(r"\d", bare) or _NUMBER_WORDS.search(bare):
        return None  # the model wrote its own number
    out = _PLACEHOLDER.sub(lambda m: placeholders[m.group(1)], t)
    return out if len(out) <= 600 else None


class LLMConverser:
    def __init__(self):
        self._client = get_client()

    async def phrase(self, *, history, situation, goal, facts, placeholders, descriptions, channel):
        return await asyncio.to_thread(
            self._phrase_sync, history, situation, goal, facts, placeholders, descriptions, channel
        )

    def _phrase_sync(self, history, situation, goal, facts, placeholders, descriptions, channel):
        style = (
            "This is a VOICE conversation: at most 2 short sentences, easy to say aloud."
            if channel == "voice"
            else "This is a chat: at most 3 short sentences."
        )
        brief = {
            "situation": situation,
            "what_your_reply_must_do": goal,
            "facts": facts,
            "placeholders_you_may_use": descriptions,
        }
        msgs = [{"role": "system", "content": PERSONA + "\n\n" + style}]
        for m in history[-8:]:
            msgs.append({"role": m["role"], "content": m["content"]})
        msgs.append(
            {
                "role": "system",
                "content": "BRIEF FOR YOUR NEXT REPLY (JSON):\n"
                + json.dumps(brief, ensure_ascii=False),
            }
        )
        kw = {"reasoning_effort": "none"}
        try:
            for _ in range(2):
                r = self._client.chat.completions.create(
                    model=deployment(fast=True), messages=msgs, max_completion_tokens=400, **kw
                )
                text = (r.choices[0].message.content or "").strip()
                out = render(text, placeholders) if text else None
                if out:
                    return out
        except Exception as e:
            log.warning("converse failed: %s", e)
            return None
        log.warning("converse draft rejected: %r", text)
        return None
