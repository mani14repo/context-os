from __future__ import annotations

import math
from collections.abc import Sequence

from pydantic import BaseModel

from contextos.embeddings import HashingEmbeddingProvider
from contextos.library import ContextOS
from contextos.models import ContextNode, ContextQuery
from contextos.protocols import EmbeddingProvider
from contextos.search import node_haystack

__all__ = ["SimilarNode", "curate", "find_similar"]


class SimilarNode(BaseModel):
    node: ContextNode
    similarity: float


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


async def find_similar(
    context_os: ContextOS,
    tenant_id: str,
    content: str,
    *,
    embeddings: EmbeddingProvider | None = None,
    threshold: float = 0.85,
    candidate_limit: int = 50,
) -> list[SimilarNode]:
    """Find existing nodes whose content is similar to `content`, for
    de-duplication before inserting new content -- the ACE paper's "grow-and-refine"
    pattern (Zhang et al., 2025, arxiv.org/abs/2510.04618), generalized to work
    against any ContextStore rather than only PostgresContextStore: this computes
    cosine similarity itself via an EmbeddingProvider instead of relying on a
    store's internal vector search, so it works with the dependency-free default
    (`HashingEmbeddingProvider`, a lexical-overlap stand-in like the rest of the
    library's deterministic defaults -- pass a real embedding model for genuine
    semantic de-duplication) against InMemoryContextStore/SQLiteContextStore too.

    `candidate_limit` bounds how many of the tenant's nodes (via `ContextOS.search()`)
    are compared against; this is a Python-side similarity computation over that
    bounded candidate set, not a database-side ANN search, so it doesn't scale the
    way `PostgresContextStore`'s own `ORDER BY embedding <=> ...` does. Results are
    sorted by similarity, highest first.
    """
    provider = embeddings or HashingEmbeddingProvider()
    target_vector = await provider.embed(content)
    candidates = await context_os.search(
        ContextQuery(tenant_id=tenant_id, query=content, max_results=candidate_limit)
    )
    scored: list[SimilarNode] = []
    for node in candidates:
        node_vector = await provider.embed(node_haystack(node) or node.node_type)
        similarity = _cosine(target_vector, node_vector)
        if similarity >= threshold:
            scored.append(SimilarNode(node=node, similarity=similarity))
    scored.sort(key=lambda item: item.similarity, reverse=True)
    return scored


async def curate(
    context_os: ContextOS,
    tenant_id: str,
    candidate: ContextNode,
    *,
    embeddings: EmbeddingProvider | None = None,
    merge_threshold: float = 0.9,
) -> ContextNode:
    """ACE's Curator role: given a candidate insight, either merge it into an
    existing near-duplicate (record positive feedback on it, reinforcing rather than
    duplicating) or ingest it as a genuinely new node. Composes `find_similar()` and
    `ContextOS.record_feedback()` -- no new storage mechanism, just the merge
    decision the ACE paper describes as "deterministic, non-LLM logic".

    Returns the reinforced existing node if a match was found above
    `merge_threshold`, otherwise the newly ingested `candidate`.
    """
    content = candidate.content or candidate.summary or candidate.title or ""
    matches = await find_similar(
        context_os,
        tenant_id,
        content,
        embeddings=embeddings,
        threshold=merge_threshold,
        candidate_limit=10,
    )
    if matches:
        return await context_os.record_feedback(tenant_id, matches[0].node.id, helpful=True)
    return await context_os.ingest(candidate)
