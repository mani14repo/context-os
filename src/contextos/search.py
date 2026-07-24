from __future__ import annotations

import math

from contextos.models import ContextNode, ContextQuery, utcnow
from contextos.text import tokenize


def score_node(query: ContextQuery, node: ContextNode) -> float | None:
    """Lexical relevance score for `node` against `query`, or None if filtered out.

    Shared by every ContextStore implementation so ranking behaves identically
    regardless of backend (in-memory, SQLite, or a future adapter).
    """
    if node.tenant_id != query.tenant_id:
        return None
    if query.memory_types and node.memory_type not in query.memory_types:
        return None
    if query.tiers and node.storage_tier not in query.tiers:
        return None
    if query.node_types and node.node_type not in query.node_types:
        return None
    if node.confidence < query.minimum_confidence:
        return None
    as_of = query.as_of or utcnow()
    if node.valid_from > as_of:
        return None
    if node.valid_to is not None and as_of >= node.valid_to:
        return None
    query_terms = tokenize(query.query)
    haystack = " ".join(filter(None, [node.title, node.summary, node.content]))
    node_terms = tokenize(haystack)
    overlap = len(query_terms & node_terms)
    lexical = overlap / math.sqrt(max(1, len(query_terms) * len(node_terms)))
    metadata_match = 0.2 if query.entity_ids and node.id in query.entity_ids else 0.0
    score = lexical + metadata_match + node.importance * 0.05
    if query_terms and score <= 0:
        return None
    return score
