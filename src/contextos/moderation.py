from __future__ import annotations

from collections.abc import Sequence

from contextos.protocols import ModerationResult

__all__ = ["KeywordModerator"]


class KeywordModerator:
    """Deterministic, dependency-free Moderator that flags content containing any
    of a caller-supplied list of terms (case-insensitive substring match).

    A structural stand-in, like SimpleCompactor/RegexRedactor/HashingEmbeddingProvider
    -- well-suited to policy enforcement with a known, fixed vocabulary (flagging a
    mention of an unannounced product codename, a banned competitor reference, or an
    internal-only term that shouldn't reach a public-facing output), not
    general-purpose toxicity/harm detection, which needs a real classifier or
    moderation API implementing the same `Moderator` protocol. There's no shipped
    default word list -- unlike `RegexRedactor`'s objectively-defined PII patterns, a
    meaningful blocklist is inherently policy-specific, so the caller supplies one.
    """

    def __init__(self, blocklist: Sequence[str]) -> None:
        self._blocklist = [term.lower() for term in blocklist]

    async def moderate(self, content: str) -> ModerationResult:
        lowered = content.lower()
        matched = [term for term in self._blocklist if term in lowered]
        return ModerationResult(flagged=bool(matched), categories=matched)
