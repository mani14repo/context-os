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
    Extractor,
    GraphStore,
    ModerationResult,
    Moderator,
    Redactor,
    TierManager,
)
from contextos.redaction import RegexRedactor
from contextos.retention import is_eligible_for_deletion
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
        redactor: Redactor | None = None,
        moderator: Moderator | None = None,
    ) -> None:
        default_store = store or InMemoryContextStore()
        self.store: ContextStore = default_store
        self.graph: GraphStore = graph or default_store  # type: ignore[assignment]
        self.compactor: Compactor = compactor or SimpleCompactor()
        self.tier_manager: TierManager = tier_manager or default_store  # type: ignore[assignment]
        self.access_log: AccessLog = access_log or default_store  # type: ignore[assignment]
        # Unlike the other five collaborators, artifact storage has no in-process
        # fallback: InMemoryContextStore/SQLiteContextStore don't implement
        # ArtifactStore, so this stays None unless you pass one explicitly.
        self.artifacts = artifacts
        self.redactor: Redactor = redactor or RegexRedactor()
        # Unlike redactor, moderation has no dependency-free default -- there's no
        # sensible built-in moderation heuristic the way RegexRedactor's PII patterns
        # are, so this stays None unless configured explicitly (same as artifacts).
        self.moderator: Moderator | None = moderator
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

    async def delete(self, tenant_id: str, node_id: UUID) -> bool:
        """Delete a node. Raises `contextos.errors.LegalHoldError` instead of deleting
        if the node has `legal_hold=True` -- see contextos.retention."""
        return await self.store.delete_node(tenant_id, node_id)

    async def edges_for(self, tenant_id: str, node_id: UUID) -> list[ContextEdge]:
        """Every edge touching this node, in either direction. Used by
        contextos.workflows to find `contradicts`/`supersedes` relationships."""
        return list(await self.graph.edges_for_node(tenant_id, node_id))

    async def record_feedback(self, tenant_id: str, node_id: UUID, *, helpful: bool) -> ContextNode:
        """Record that a node was judged helpful or harmful after being used --
        e.g. by an agent's reflection step, following the ACE paper's (Zhang et al.,
        2025, arxiv.org/abs/2510.04618) pattern of tracking per-bullet helpful/harmful
        counters. Increments `metadata["feedback_helpful_count"]` or
        `metadata["feedback_harmful_count"]` and re-ingests the node.

        Like any other update, this goes through `put_node()`, so it creates a new
        version -- the same immutable-history tradeoff `compact()` and `move()`
        already have, not a special case here. A node that receives frequent
        feedback will accumulate frequent versions; if that churn matters for your
        use case, batch feedback calls rather than recording each one individually.
        Raises `KeyError` if the node doesn't exist for this tenant.
        """
        node = await self.store.get_node(tenant_id, node_id)
        if node is None:
            raise KeyError(node_id)
        key = "feedback_helpful_count" if helpful else "feedback_harmful_count"
        node.metadata[key] = int(node.metadata.get(key, 0)) + 1
        return await self.ingest(node)

    async def ingest_source(self, extractor: Extractor, tenant_id: str) -> list[ContextNode]:
        """Run an Extractor against its configured source and ingest() every
        ContextNode it produces. This is the ingestion-pipeline entry point: a
        DocumentExtractor(path), APIExtractor(url), DatabaseExtractor(dsn, query),
        KafkaEventExtractor(topic), MattermostExtractor(channel), MediaExtractor(...),
        or GitHubIssuesExtractor(repo) (see contextos.ingestion) each turn their
        specific source into ContextNodes; this method is the same one line
        regardless of which one you're using. Nodes are ingested in the order the
        extractor returns them, sequentially -- an Extractor that needs bulk/parallel
        writes should call context_os.ingest() directly instead."""
        with start_span(
            "contextos.ingest_source", tenant_id=tenant_id, extractor=type(extractor).__name__
        ) as span:
            extracted = await extractor.extract(tenant_id=tenant_id)
            ingested = [await self.ingest(node) for node in extracted]
            span.set_attribute("contextos.ingested_count", len(ingested))
        return ingested

    async def redact(self, content: str) -> str:
        """Apply the configured Redactor (default: contextos.redaction.RegexRedactor,
        a deterministic PII-pattern stripper) to a piece of text. This is a data
        transformation, not access control -- ContextOS has no authorization concept
        (see README "Known limitations"), so it doesn't decide *when* to redact based
        on who's asking; callers apply it explicitly, e.g. before returning
        `classification=CONFIDENTIAL` content to an untrusted destination."""
        return await self.redactor.redact(content)

    async def moderate(self, content: str) -> ModerationResult:
        """Run the configured Moderator (content-safety screening -- e.g. an LLM
        moderation API, or `contextos.moderation.KeywordModerator` for
        fixed-vocabulary policy checks) against a piece of text. Unlike `redact()`,
        this has no dependency-free default, so it raises RuntimeError if no
        `moderator` was configured, matching `store_artifact()`/`load_artifact()`'s
        pattern for artifacts. ContextOS never calls this automatically -- apply it
        explicitly, e.g. before `ingest()` on untrusted input, or before returning
        `assemble()` output to an end user."""
        if self.moderator is None:
            raise RuntimeError("No Moderator configured on this ContextOS instance")
        return await self.moderator.moderate(content)

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

    async def apply_retention_policy(self, tenant_id: str) -> list[ContextNode]:
        """Delete every node for a tenant whose `retention_until` has passed, skipping
        any node with `legal_hold=True` (see `contextos.retention.is_eligible_for_deletion`).
        Returns the nodes that were deleted. Limited to a tenant's first 200 nodes
        (`ContextQuery.max_results` ceiling) per call, same as `apply_tiering_policy()`."""
        with start_span("contextos.apply_retention_policy", tenant_id=tenant_id) as span:
            query = ContextQuery(tenant_id=tenant_id, query="", max_results=200)
            nodes = await self.store.search(query)
            deleted: list[ContextNode] = []
            for node in nodes:
                if is_eligible_for_deletion(node) and await self.store.delete_node(
                    tenant_id, node.id
                ):
                    deleted.append(node)
            span.set_attribute("contextos.deleted_count", len(deleted))
        return deleted
