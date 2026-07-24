from __future__ import annotations

import re

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("PHONE", re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")),
    ("CREDIT_CARD", re.compile(r"\b\d(?:[ -]?\d){12,15}\b")),
]


class RegexRedactor:
    """Deterministic, dependency-free Redactor. Strips common PII patterns (emails,
    US-style SSNs and phone numbers, credit-card-like digit sequences) via regex and
    replaces each match with `[REDACTED:<TYPE>]`.

    A structural stand-in, like SimpleCompactor -- it catches obvious, well-formed
    patterns, not names, addresses, or context-dependent sensitive information. Swap
    in an NER/LLM-backed Redactor for production-grade redaction; this exists so the
    `Redactor` protocol and `ContextOS.redact()` have a working default with no API
    key or heavy dependency required.

    Patterns are applied in order from most to least specific (email/SSN/phone before
    the broad credit-card digit-run pattern), and each substitution removes the raw
    digits it matched -- so a later, broader pattern can't re-match text an earlier
    pattern already redacted.
    """

    async def redact(self, content: str) -> str:
        redacted = content
        for label, pattern in _PATTERNS:
            redacted = pattern.sub(f"[REDACTED:{label}]", redacted)
        return redacted
