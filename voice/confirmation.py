"""Deterministic spoken-approval gate. Pure Python: no LLM, no I/O.

Accept only a clear affirmative with no hedge, change word, or conflicting number.
"""

import re

_AFFIRM = {
    "yes",
    "yeah",
    "yep",
    "yup",
    "yaa",
    "ya",
    "s",
    "confirm",
    "confirmed",
    "approve",
    "approved",
    "haan",
    "han",
    "ha",
    "sure",
    "ok",
    "okay",
    "go",
    "proceed",
    "place",
    "order",
    "do",
    "it",
    "karo",
    "kar",
    "theek",
    "thik",
    "hai",
    "please",
    "plz",
    "pls",
    "the",
    "this",
    "that",
    "ahead",
    "right",
    "correct",
    "perfect",
    "fine",
    "good",
    "now",
    "and",
    "sounds",
    "looks",
    "great",
}
_CORE_AFFIRM = {
    "yes",
    "yeah",
    "yep",
    "yup",
    "yaa",
    "ya",
    "s",
    "confirm",
    "confirmed",
    "approve",
    "approved",
    "haan",
    "han",
    "go",
    "proceed",
    "place",
    "karo",
    "sure",
    "okay",
    "ok",
    "theek",
    "thik",
}
_BLOCK = {
    "no",
    "nope",
    "nah",
    "not",
    "dont",
    "don't",
    "wait",
    "hold",
    "actually",
    "but",
    "change",
    "however",
    "instead",
    "cancel",
    "stop",
    "nahi",
    "nahin",
    "ruko",
    "mat",
    "except",
    "unless",
    "maybe",
    "hmm",
    "um",
    "uh",
    "remove",
    "add",
    "swap",
    "cheaper",
    "different",
    "edit",
    "what",
    "why",
    "how",
    "which",
    "when",
    "repeat",
    "again",
}
MIN_CONFIDENCE = 0.5


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9'\u0900-\u097f]+", text.lower().replace("’", "'"))


def is_confirmed(utterance: str | None, confidence: float | None = None) -> bool:
    """True only for a clear, unhedged yes."""
    if not utterance or not utterance.strip():
        return False
    if confidence is not None and confidence < MIN_CONFIDENCE:
        return False
    toks = _tokens(utterance)
    if not toks or len(toks) > 10:
        return False
    if any(t in _BLOCK for t in toks):
        return False
    if any(t.isdigit() for t in toks):  # any number might contradict the read-back total
        return False
    if not all(t in _AFFIRM for t in toks):
        return False
    return any(t in _CORE_AFFIRM for t in toks)
