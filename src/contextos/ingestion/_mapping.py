from __future__ import annotations

import json
from typing import Any

from contextos.models import Classification, ContextNode, MemoryType

__all__ = ["record_to_node"]


def record_to_node(
    tenant_id: str,
    record: dict[str, Any],
    *,
    content_field: str,
    title_field: str | None,
    id_field: str | None,
    node_type: str,
    memory_type: MemoryType,
    classification: Classification,
    importance: float,
    source_type: str,
    extra_metadata: dict[str, Any] | None = None,
) -> ContextNode:
    """Shared field-mapping logic for extractors whose source is a flat record --
    a dict of named fields (an API JSON object, a database row). Not used by
    extractors with a fixed, non-configurable schema (GitHub issues, Mattermost
    messages), which build ContextNode directly instead."""
    content = record.get(content_field)
    if content is None:
        content = json.dumps(record, default=str)
    title = record.get(title_field) if title_field else None
    metadata: dict[str, Any] = {"source_type": source_type, **(extra_metadata or {})}
    if id_field and id_field in record:
        metadata["source_id"] = record[id_field]
    return ContextNode(
        tenant_id=tenant_id,
        node_type=node_type,
        memory_type=memory_type,
        classification=classification,
        title=str(title) if title is not None else None,
        content=str(content),
        importance=importance,
        metadata=metadata,
    )
