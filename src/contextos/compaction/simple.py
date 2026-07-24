from __future__ import annotations

import re

from contextos.models import CompressionLevel, ContextNode, ContextRepresentation

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


class SimpleCompactor:
    """Deterministic fallback compactor; replace with an LLM-backed implementation."""

    async def compact(self, node: ContextNode, level: CompressionLevel) -> ContextRepresentation:
        source = node.content or node.summary or node.title or ""
        sentences = [item.strip() for item in _SENTENCE_RE.split(source) if item.strip()]
        limits = {
            CompressionLevel.METADATA: 0,
            CompressionLevel.ONE_LINE: 1,
            CompressionLevel.COMPACT: 3,
            CompressionLevel.DETAILED: 8,
            CompressionLevel.FULL: len(sentences),
            CompressionLevel.ORIGINAL: len(sentences),
        }
        if level is CompressionLevel.METADATA:
            content = node.title or node.summary or ""
        else:
            content = " ".join(sentences[: limits[level]]) or source
        return ContextRepresentation(
            level=level,
            content=content,
            token_count=max(1, len(content.split())) if content else 0,
        )
