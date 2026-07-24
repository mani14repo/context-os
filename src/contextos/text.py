from __future__ import annotations

import re
from collections import Counter

_TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")


def tokenize(text: str) -> set[str]:
    return {term.lower() for term in _TOKEN_RE.findall(text)}


def tokenize_counts(text: str) -> Counter[str]:
    """Like tokenize(), but keeps term frequency instead of collapsing to a set."""
    return Counter(term.lower() for term in _TOKEN_RE.findall(text))
