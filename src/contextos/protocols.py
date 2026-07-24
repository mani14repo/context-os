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


class TierManager(Protocol):
    async def move(self, tenant_id: str, node_id: UUID, tier: StorageTier) -> ContextNode: ...


class Compactor(Protocol):
    async def compact(self, node: ContextNode, level: CompressionLevel) -> ContextRepresentation: ...


class AccessLog(Protocol):
    async def record(self, tenant_id: str, node_id: UUID, agent: str, task: str) -> None: ...
    async def last_accessed(self, tenant_id: str, node_id: UUID) -> datetime | None: ...
