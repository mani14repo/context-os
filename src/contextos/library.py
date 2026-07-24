from __future__ import annotations

from uuid import UUID

from contextos.compaction.simple import SimpleCompactor
from contextos.models import (
    CompressionLevel,
    ContextEdge,
    ContextNode,
    ContextPackage,
    ContextQuery,
    ContextRepresentation,
    ContextRequest,
    StorageTier,
)
from contextos.orchestration.orchestrator import ContextOrchestrator
from contextos.protocols import Compactor, ContextStore, GraphStore, TierManager
from contextos.storage.memory import InMemoryContextStore


class ContextOS:
    """High-level facade for embedding ContextOS in an application."""

    def __init__(
        self,
        store: ContextStore | None = None,
        graph: GraphStore | None = None,
        compactor: Compactor | None = None,
        tier_manager: TierManager | None = None,
    ) -> None:
        default_store = store or InMemoryContextStore()
        self.store: ContextStore = default_store
        self.graph: GraphStore = graph or default_store  # type: ignore[assignment]
        self.compactor: Compactor = compactor or SimpleCompactor()
        self.tier_manager: TierManager = tier_manager or default_store  # type: ignore[assignment]
        self.orchestrator = ContextOrchestrator(self.store, self.graph, self.compactor)

    async def ingest(self, node: ContextNode) -> ContextNode:
        return await self.store.put_node(node)

    async def link(self, edge: ContextEdge) -> ContextEdge:
        return await self.graph.put_edge(edge)

    async def search(self, query: ContextQuery) -> list[ContextNode]:
        return list(await self.store.search(query))

    async def assemble(self, request: ContextRequest) -> ContextPackage:
        return await self.orchestrator.assemble(request)

    async def compact(self, node: ContextNode, level: CompressionLevel) -> ContextRepresentation:
        representation = await self.compactor.compact(node, level)
        node.representations.append(representation)
        await self.store.put_node(node)
        return representation

    async def move(self, tenant_id: str, node_id: UUID, tier: StorageTier) -> ContextNode:
        return await self.tier_manager.move(tenant_id, node_id, tier)
