import pytest

from contextos import (
    CompressionLevel,
    ContextEdge,
    ContextNode,
    ContextOS,
    ContextRequest,
    MemoryType,
    StorageTier,
)
from contextos.models import ContextRepresentation


@pytest.mark.asyncio
async def test_ingest_link_search_and_assemble() -> None:
    os = ContextOS()
    convention = await os.ingest(
        ContextNode(
            tenant_id="t1",
            node_type="project_convention",
            memory_type=MemoryType.SEMANTIC,
            title="Release convention",
            content="Stable releases use semantic versioning and include a changelog.",
            importance=0.9,
        )
    )
    release_note = await os.ingest(
        ContextNode(
            tenant_id="t1",
            node_type="release_note",
            memory_type=MemoryType.ARTIFACT,
            title="Version 1.2 release note",
            content="Version 1.2 includes a changelog and uses semantic versioning.",
            importance=0.8,
        )
    )
    await os.link(
        ContextEdge(
            tenant_id="t1",
            source_node_id=release_note.id,
            target_node_id=convention.id,
            relationship="follows",
        )
    )
    package = await os.assemble(
        ContextRequest(
            tenant_id="t1",
            task="What is required for a stable release?",
            agent="release-assistant",
            memory_scopes={MemoryType.SEMANTIC, MemoryType.ARTIFACT},
            token_budget=300,
        )
    )
    assert len(package.items) == 2
    assert package.token_count <= 300
    assert convention.id in package.provenance


@pytest.mark.asyncio
async def test_tenant_isolation_and_tiering() -> None:
    os = ContextOS()
    node = await os.ingest(
        ContextNode(
            tenant_id="tenant-a",
            node_type="fact",
            memory_type=MemoryType.SEMANTIC,
            content="Tenant-specific project fact",
        )
    )
    moved = await os.move("tenant-a", node.id, StorageTier.COLD)
    assert moved.storage_tier is StorageTier.COLD
    assert await os.store.get_node("tenant-b", node.id) is None


@pytest.mark.asyncio
async def test_ranking_prefers_relevant_node_over_merely_important_node() -> None:
    os = ContextOS()
    relevant = await os.ingest(
        ContextNode(
            tenant_id="t1",
            node_type="fact",
            memory_type=MemoryType.SEMANTIC,
            title="Kubernetes upgrade checklist",
            content="Kubernetes cluster upgrades require draining nodes before the control plane bump.",
            importance=0.2,
        )
    )
    await os.ingest(
        ContextNode(
            tenant_id="t1",
            node_type="fact",
            memory_type=MemoryType.SEMANTIC,
            title="Coffee machine maintenance",
            content="Descale the office coffee machine every quarter with a vinegar solution.",
            importance=0.9,
        )
    )
    package = await os.assemble(
        ContextRequest(
            tenant_id="t1",
            task="How do I upgrade the Kubernetes control plane?",
            agent="ops-assistant",
            token_budget=1000,
        )
    )
    assert package.items
    assert package.items[0].node.id == relevant.id


@pytest.mark.asyncio
async def test_assemble_falls_back_to_cold_tier_when_hot_warm_empty() -> None:
    os = ContextOS()
    archived = await os.ingest(
        ContextNode(
            tenant_id="t1",
            node_type="fact",
            memory_type=MemoryType.SEMANTIC,
            title="Disaster recovery runbook",
            content="The disaster recovery cutover is triggered manually by the on-call engineer.",
            storage_tier=StorageTier.COLD,
        )
    )
    package = await os.assemble(
        ContextRequest(
            tenant_id="t1",
            task="How is disaster recovery cutover triggered?",
            agent="ops-assistant",
            token_budget=1000,
        )
    )
    assert archived.id in package.provenance


@pytest.mark.asyncio
async def test_custom_compactor_is_used_instead_of_default() -> None:
    class StubCompactor:
        async def compact(self, node: ContextNode, level: CompressionLevel) -> ContextRepresentation:
            return ContextRepresentation(level=level, content="stub", token_count=1)

    os = ContextOS(compactor=StubCompactor())
    node = await os.ingest(
        ContextNode(
            tenant_id="t1",
            node_type="fact",
            memory_type=MemoryType.SEMANTIC,
            content="Some content",
        )
    )
    representation = await os.compact(node, CompressionLevel.COMPACT)
    assert representation.content == "stub"
