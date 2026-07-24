from __future__ import annotations

import math

from contextos.models import ContextNode, ContextQuery, utcnow
from contextos.text import tokenize


def node_haystack(node: ContextNode) -> str:
    """The searchable text of a node -- shared so lexical scoring and embedding
    generation (contextos.storage.postgres) always look at the same fields."""
    return " ".join(filter(None, [node.title, node.summary, node.content]))


def passes_filters(query: ContextQuery, node: ContextNode) -> bool:
    """Tenant, memory-type, tier, node-type, confidence, and temporal-validity
    filters shared by every ContextStore implementation, independent of how each
    backend ranks relevance (lexical overlap, pgvector distance, ...)."""
    if node.tenant_id != query.tenant_id:
        return False
    if query.memory_types and node.memory_type not in query.memory_types:
        return False
    if query.tiers and node.storage_tier not in query.tiers:
        return False
    if query.node_types and node.node_type not in query.node_types:
        return False
    if node.confidence < query.minimum_confidence:
        return False
    as_of = query.as_of or utcnow()
    if node.valid_from > as_of:
        return False
    return not (node.valid_to is not None and as_of >= node.valid_to)


def score_node(query: ContextQuery, node: ContextNode) -> float | None:
    """Lexical relevance score for `node` against `query`, or None if filtered out.

    Shared by the in-memory and SQLite stores so their ranking behaves identically.
    """
    if not passes_filters(query, node):
        return None
    query_terms = tokenize(query.query)
    node_terms = tokenize(node_haystack(node))
    overlap = len(query_terms & node_terms)
    lexical = overlap / math.sqrt(max(1, len(query_terms) * len(node_terms)))
    metadata_match = 0.2 if query.entity_ids and node.id in query.entity_ids else 0.0
    score = lexical + metadata_match + node.importance * 0.05
    if query_terms and score <= 0:
        return None
    return score
