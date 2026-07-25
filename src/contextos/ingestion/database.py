from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import asyncpg

from contextos.ingestion._mapping import record_to_node
from contextos.models import Classification, ContextNode, MemoryType

__all__ = ["DatabaseExtractor"]


class DatabaseExtractor:
    """Runs a SQL query against PostgreSQL and maps each result row to a
    ContextNode via the same field-mapping approach as APIExtractor -- most REST
    APIs and SQL queries both ultimately produce "a list of records with named
    fields", so a query result and a JSON array are handled identically once
    fetched. Reuses `asyncpg` (the same driver `PostgresContextStore` uses), so no
    dependency beyond `pip install -e ".[postgres]"`. Opens and closes a dedicated
    connection per extract() call -- for repeated extraction, wrap this in your own
    connection-pooling if needed.
    """

    def __init__(
        self,
        dsn: str,
        query: str,
        *,
        query_args: Sequence[Any] = (),
        content_field: str = "content",
        title_field: str | None = "title",
        id_field: str | None = None,
        node_type: str = "database_record",
        memory_type: MemoryType = MemoryType.SEMANTIC,
        classification: Classification = Classification.INTERNAL,
        importance: float = 0.5,
    ) -> None:
        self._dsn = dsn
        self._query = query
        self._query_args = query_args
        self._content_field = content_field
        self._title_field = title_field
        self._id_field = id_field
        self._node_type = node_type
        self._memory_type = memory_type
        self._classification = classification
        self._importance = importance

    def _to_node(self, tenant_id: str, record: dict[str, Any]) -> ContextNode:
        return record_to_node(
            tenant_id,
            record,
            content_field=self._content_field,
            title_field=self._title_field,
            id_field=self._id_field,
            node_type=self._node_type,
            memory_type=self._memory_type,
            classification=self._classification,
            importance=self._importance,
            source_type="database",
        )

    async def extract(self, *, tenant_id: str) -> list[ContextNode]:
        conn = await asyncpg.connect(self._dsn)
        try:
            rows = await conn.fetch(self._query, *self._query_args)
        finally:
            await conn.close()
        return [self._to_node(tenant_id, dict(row)) for row in rows]
