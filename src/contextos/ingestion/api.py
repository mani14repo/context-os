from __future__ import annotations

from typing import Any

import httpx

from contextos.ingestion._mapping import record_to_node
from contextos.models import Classification, ContextNode, MemoryType

__all__ = ["APIExtractor"]


def _resolve_path(payload: Any, dotted_path: str | None) -> Any:
    if not dotted_path:
        return payload
    current = payload
    for segment in dotted_path.split("."):
        if not isinstance(current, dict) or segment not in current:
            raise KeyError(f"records_path segment {segment!r} not found in response")
        current = current[segment]
    return current


class APIExtractor:
    """Fetches JSON from a REST API endpoint and maps each record to a ContextNode.

    Handles the common shape: a GET response is either a single JSON object, a bare
    list of objects, or a list nested under a key (`records_path`, dotted -- e.g.
    "data.items"). Each record becomes one ContextNode via a configurable field
    mapping (`content_field`/`title_field`/`id_field`); this covers most REST APIs
    and SQL-query-shaped results without a source-specific extractor. Requires
    `pip install -e ".[http]"`.
    """

    def __init__(
        self,
        url: str,
        *,
        records_path: str | None = None,
        content_field: str = "content",
        title_field: str | None = "title",
        id_field: str | None = None,
        node_type: str = "api_record",
        memory_type: MemoryType = MemoryType.SEMANTIC,
        classification: Classification = Classification.INTERNAL,
        importance: float = 0.5,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._url = url
        self._records_path = records_path
        self._content_field = content_field
        self._title_field = title_field
        self._id_field = id_field
        self._node_type = node_type
        self._memory_type = memory_type
        self._classification = classification
        self._importance = importance
        self._headers = headers
        self._params = params
        self._timeout = timeout

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
            source_type="api",
            extra_metadata={"source_url": self._url},
        )

    async def extract(self, *, tenant_id: str) -> list[ContextNode]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(self._url, headers=self._headers, params=self._params)
            response.raise_for_status()
            payload = response.json()
        records = _resolve_path(payload, self._records_path)
        if isinstance(records, dict):
            records = [records]
        return [self._to_node(tenant_id, record) for record in records]
