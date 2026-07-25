from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from contextos.models import (
    CompressionLevel,
    ContextEdge,
    ContextNode,
    ContextQuery,
    ContextRepresentation,
    StorageTier,
)


class ContextStore(Protocol):
    async def put_node(self, node: ContextNode) -> ContextNode: ...
    async def get_node(self, tenant_id: str, node_id: UUID) -> ContextNode | None: ...
    async def get_history(self, tenant_id: str, node_id: UUID) -> Sequence[ContextNode]: ...
    async def search(self, query: ContextQuery) -> Sequence[ContextNode]: ...
    async def delete_node(self, tenant_id: str, node_id: UUID) -> bool: ...


class GraphStore(Protocol):
    async def put_edge(self, edge: ContextEdge) -> ContextEdge: ...
    async def neighbors(
        self, tenant_id: str, node_ids: Sequence[UUID], depth: int = 1
    ) -> Sequence[ContextNode]: ...
    async def edges_for_node(self, tenant_id: str, node_id: UUID) -> Sequence[ContextEdge]: ...


class TierManager(Protocol):
    async def move(self, tenant_id: str, node_id: UUID, tier: StorageTier) -> ContextNode: ...


class Compactor(Protocol):
    async def compact(self, node: ContextNode, level: CompressionLevel) -> ContextRepresentation: ...


class AccessLog(Protocol):
    async def record(self, tenant_id: str, node_id: UUID, agent: str, task: str) -> None: ...
    async def last_accessed(self, tenant_id: str, node_id: UUID) -> datetime | None: ...


class EmbeddingProvider(Protocol):
    async def embed(self, text: str) -> Sequence[float]: ...


class Extractor(Protocol):
    """Pulls raw content from a specific external source and turns it into
    ContextNodes ready for ContextOS.ingest(). Each concrete Extractor owns its own
    source-specific configuration (a file path, a URL, a DB query, a topic, a
    channel, a repo) via its constructor -- extract() itself takes only the tenant_id
    every ingested node needs. See contextos.ingestion for reference implementations
    (documents, generic JSON APIs, SQL databases, Kafka, Mattermost, blob storage,
    GitHub Issues) and ContextOS.ingest_source() for the facade entry point."""

    async def extract(self, *, tenant_id: str) -> Sequence[ContextNode]: ...


class FullContextStore(ContextStore, GraphStore, TierManager, AccessLog, Protocol):
    """Convenience union of the four protocols a complete storage backend typically
    implements together, as InMemoryContextStore, SQLiteContextStore, and
    PostgresContextStore all do. Used to type wrappers/decorators (e.g.
    RedisCachedContextStore) that need the full surface of an underlying store."""


class Redactor(Protocol):
    async def redact(self, content: str) -> str: ...


class ArtifactStore(Protocol):
    """Object storage for the large/original content a ContextNode.content_pointer
    refers to -- the "graph-content separation" design principle: nodes carry
    pointers, large artifacts live in a blob store, not in the node's `content` field.
    `put()` returns an opaque pointer string that `get()`/`delete()` accept back."""

    async def put(
        self, tenant_id: str, key: str, data: bytes, content_type: str | None = None
    ) -> str: ...
    async def get(self, pointer: str) -> bytes: ...
    async def delete(self, pointer: str) -> bool: ...
