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
from contextos.protocols import (
    AccessLog,
    ArtifactStore,
    Compactor,
    ContextStore,
    GraphStore,
    TierManager,
)
from contextos.storage.memory import InMemoryContextStore
from contextos.tiering import suggest_tier
from contextos.tracing import start_span


class ContextOS:
    """High-level facade for embedding ContextOS in an application."""

    def __init__(
        self,
        store: ContextStore | None = None,
        graph: GraphStore | None = None,
        compactor: Compactor | None = None,
        tier_manager: TierManager | None = None,
        access_log: AccessLog | None = None,
        artifacts: ArtifactStore | None = None,
    ) -> None:
        default_store = store or InMemoryContextStore()
        self.store: ContextStore = default_store
        self.graph: GraphStore = graph or default_store  # type: ignore[assignment]
        self.compactor: Compactor = compactor or SimpleCompactor()
        self.tier_manager: TierManager = tier_manager or default_store  # type: ignore[assignment]
        self.access_log: AccessLog = access_log or default_store  # type: ignore[assignment]
        # Unlike the other four collaborators, artifact storage has no in-process
        # fallback: InMemoryContextStore/SQLiteContextStore don't implement
        # ArtifactStore, so this stays None unless you pass one explicitly.
        self.artifacts = artifacts
        self.orchestrator = ContextOrchestrator(
            self.store, self.graph, self.compactor, self.access_log
        )

    async def ingest(self, node: ContextNode) -> ContextNode:
        with start_span(
            "contextos.ingest", tenant_id=node.tenant_id, node_type=node.node_type
        ):
            return await self.store.put_node(node)

    async def link(self, edge: ContextEdge) -> ContextEdge:
        with start_span(
            "contextos.link", tenant_id=edge.tenant_id, relationship=edge.relationship
        ):
            return await self.graph.put_edge(edge)

    async def search(self, query: ContextQuery) -> list[ContextNode]:
        return list(await self.store.search(query))

    async def history(self, tenant_id: str, node_id: UUID) -> list[ContextNode]:
        """Prior versions of a node, oldest first. Empty if the node doesn't exist or
        has never been updated -- see the immutability note on `ContextStore.put_node`."""
        return list(await self.store.get_history(tenant_id, node_id))

    async def assemble(self, request: ContextRequest) -> ContextPackage:
        return await self.orchestrator.assemble(request)

    async def compact(self, node: ContextNode, level: CompressionLevel) -> ContextRepresentation:
        with start_span(
            "contextos.compact", tenant_id=node.tenant_id, node_id=str(node.id), level=level.value
        ):
            representation = await self.compactor.compact(node, level)
            node.representations.append(representation)
            await self.store.put_node(node)
            return representation

    async def move(self, tenant_id: str, node_id: UUID, tier: StorageTier) -> ContextNode:
        with start_span(
            "contextos.move", tenant_id=tenant_id, node_id=str(node_id), tier=tier.value
        ):
            return await self.tier_manager.move(tenant_id, node_id, tier)

    async def store_artifact(
        self, tenant_id: str, key: str, data: bytes, content_type: str | None = None
    ) -> str:
        """Write large/original content to the configured ArtifactStore and return a
        pointer suitable for ContextNode.content_pointer. Raises RuntimeError if no
        `artifacts` collaborator was configured on this ContextOS instance."""
        if self.artifacts is None:
            raise RuntimeError("No ArtifactStore configured on this ContextOS instance")
        return await self.artifacts.put(tenant_id, key, data, content_type)

    async def load_artifact(self, pointer: str) -> bytes:
        if self.artifacts is None:
            raise RuntimeError("No ArtifactStore configured on this ContextOS instance")
        return await self.artifacts.get(pointer)

    async def apply_tiering_policy(self, tenant_id: str) -> list[ContextNode]:
        """Re-tier every node for a tenant using contextos.tiering.suggest_tier(), based
        on access recency (from `access_log`), importance, and the `active_workflow`/
        `retention_required` metadata flags. Returns the nodes that were moved. Limited
        to a tenant's first 200 nodes (ContextQuery.max_results ceiling) per call."""
        with start_span("contextos.apply_tiering_policy", tenant_id=tenant_id) as span:
            query = ContextQuery(tenant_id=tenant_id, query="", max_results=200)
            nodes = await self.store.search(query)
            moved: list[ContextNode] = []
            for node in nodes:
                last_accessed = await self.access_log.last_accessed(tenant_id, node.id)
                suggested = suggest_tier(node, last_accessed=last_accessed)
                if suggested != node.storage_tier:
                    moved.append(await self.tier_manager.move(tenant_id, node.id, suggested))
            span.set_attribute("contextos.moved_count", len(moved))
        return moved
