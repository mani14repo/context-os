from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")


def tokenize(text: str) -> set[str]:
    return {term.lower() for term in _TOKEN_RE.findall(text)}
