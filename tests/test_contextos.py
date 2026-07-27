from datetime import timedelta

import pytest

from contextos import (
    CompressionLevel,
    ContextEdge,
    ContextNode,
    ContextOS,
    ContextQuery,
    ContextRequest,
    MemoryType,
    StorageTier,
)
from contextos.errors import LegalHoldError
from contextos.models import ContextRepresentation, utcnow
from contextos.tiering import suggest_tier


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


@pytest.mark.asyncio
async def test_update_creates_version_and_preserves_history() -> None:
    os = ContextOS()
    node = await os.ingest(
        ContextNode(tenant_id="t1", node_type="fact", memory_type=MemoryType.SEMANTIC, content="v1")
    )
    assert node.version == 1

    node.content = "v2"
    updated = await os.ingest(node)
    assert updated.version == 2

    history = await os.history("t1", node.id)
    assert len(history) == 1
    assert history[0].content == "v1"
    assert history[0].version == 1


@pytest.mark.asyncio
async def test_update_cannot_change_tenant_id() -> None:
    os = ContextOS()
    node = await os.ingest(
        ContextNode(tenant_id="t1", node_type="fact", memory_type=MemoryType.SEMANTIC)
    )
    node.tenant_id = "t2"
    with pytest.raises(ValueError):
        await os.ingest(node)


@pytest.mark.asyncio
async def test_expired_node_is_excluded_from_search() -> None:
    os = ContextOS()
    await os.ingest(
        ContextNode(
            tenant_id="t1",
            node_type="fact",
            memory_type=MemoryType.SEMANTIC,
            content="Kubernetes upgrade notes",
            valid_to=utcnow() - timedelta(days=1),
        )
    )
    results = await os.search(ContextQuery(tenant_id="t1", query="Kubernetes"))
    assert results == []


@pytest.mark.asyncio
async def test_not_yet_valid_node_is_excluded_from_search() -> None:
    os = ContextOS()
    await os.ingest(
        ContextNode(
            tenant_id="t1",
            node_type="fact",
            memory_type=MemoryType.SEMANTIC,
            content="Kubernetes upgrade notes",
            valid_from=utcnow() + timedelta(days=1),
        )
    )
    results = await os.search(ContextQuery(tenant_id="t1", query="Kubernetes"))
    assert results == []


@pytest.mark.asyncio
async def test_assemble_records_access() -> None:
    os = ContextOS()
    node = await os.ingest(
        ContextNode(
            tenant_id="t1",
            node_type="fact",
            memory_type=MemoryType.SEMANTIC,
            title="Release convention",
            content="Stable releases use semantic versioning.",
            importance=0.9,
        )
    )
    assert await os.access_log.last_accessed("t1", node.id) is None
    await os.assemble(
        ContextRequest(
            tenant_id="t1", task="What about stable releases?", agent="assistant", token_budget=300
        )
    )
    assert await os.access_log.last_accessed("t1", node.id) is not None


def test_suggest_tier_rules() -> None:
    now = utcnow()
    active = ContextNode(
        tenant_id="t1",
        node_type="fact",
        memory_type=MemoryType.SEMANTIC,
        metadata={"active_workflow": True},
    )
    assert suggest_tier(active, last_accessed=None, now=now) is StorageTier.HOT

    recently_accessed = ContextNode(
        tenant_id="t1", node_type="fact", memory_type=MemoryType.SEMANTIC, importance=0.1
    )
    assert suggest_tier(recently_accessed, last_accessed=now, now=now) is StorageTier.WARM

    important = ContextNode(
        tenant_id="t1", node_type="fact", memory_type=MemoryType.SEMANTIC, importance=0.9
    )
    assert suggest_tier(important, last_accessed=None, now=now) is StorageTier.WARM

    retained = ContextNode(
        tenant_id="t1",
        node_type="fact",
        memory_type=MemoryType.SEMANTIC,
        importance=0.1,
        metadata={"retention_required": True},
    )
    assert suggest_tier(retained, last_accessed=None, now=now) is StorageTier.COLD

    stale = ContextNode(
        tenant_id="t1", node_type="fact", memory_type=MemoryType.SEMANTIC, importance=0.1
    )
    assert suggest_tier(stale, last_accessed=None, now=now) is StorageTier.ARCHIVE


@pytest.mark.asyncio
async def test_apply_tiering_policy_moves_stale_low_importance_node() -> None:
    os = ContextOS()
    node = await os.ingest(
        ContextNode(tenant_id="t1", node_type="fact", memory_type=MemoryType.SEMANTIC, importance=0.1)
    )
    assert node.storage_tier is StorageTier.WARM  # default

    moved = await os.apply_tiering_policy("t1")
    assert len(moved) == 1
    assert moved[0].storage_tier is StorageTier.ARCHIVE


@pytest.mark.asyncio
async def test_delete_raises_legal_hold_error() -> None:
    os = ContextOS()
    node = await os.ingest(
        ContextNode(
            tenant_id="t1",
            node_type="fact",
            memory_type=MemoryType.SEMANTIC,
            legal_hold=True,
        )
    )
    with pytest.raises(LegalHoldError):
        await os.delete("t1", node.id)
    # Node must still exist -- the delete was blocked, not silently partial.
    assert await os.store.get_node("t1", node.id) is not None


@pytest.mark.asyncio
async def test_delete_without_legal_hold_succeeds() -> None:
    os = ContextOS()
    node = await os.ingest(
        ContextNode(tenant_id="t1", node_type="fact", memory_type=MemoryType.SEMANTIC)
    )
    assert await os.delete("t1", node.id) is True
    assert await os.store.get_node("t1", node.id) is None


@pytest.mark.asyncio
async def test_edges_for_returns_edges_touching_node_in_either_direction() -> None:
    os = ContextOS()
    a = await os.ingest(
        ContextNode(tenant_id="t1", node_type="fact", memory_type=MemoryType.SEMANTIC)
    )
    b = await os.ingest(
        ContextNode(tenant_id="t1", node_type="fact", memory_type=MemoryType.SEMANTIC)
    )
    c = await os.ingest(
        ContextNode(tenant_id="t1", node_type="fact", memory_type=MemoryType.SEMANTIC)
    )
    await os.link(
        ContextEdge(tenant_id="t1", source_node_id=a.id, target_node_id=b.id, relationship="supports")
    )
    await os.link(
        ContextEdge(tenant_id="t1", source_node_id=c.id, target_node_id=a.id, relationship="contradicts")
    )

    edges = await os.edges_for("t1", a.id)
    relationships = {edge.relationship for edge in edges}
    assert relationships == {"supports", "contradicts"}


@pytest.mark.asyncio
async def test_simple_compactor_reports_tokens_saved_for_a_truncated_level() -> None:
    from contextos.compaction.simple import SimpleCompactor

    node = ContextNode(
        tenant_id="t1",
        node_type="doc",
        memory_type=MemoryType.SEMANTIC,
        content="One. Two. Three. Four. Five. Six. Seven. Eight. Nine. Ten.",
    )
    representation = await SimpleCompactor().compact(node, CompressionLevel.ONE_LINE)
    assert representation.tokens_saved is not None
    assert representation.tokens_saved > 0
    assert representation.token_count is not None
    assert representation.tokens_saved == 10 - representation.token_count


@pytest.mark.asyncio
async def test_simple_compactor_reports_zero_tokens_saved_for_full_level() -> None:
    from contextos.compaction.simple import SimpleCompactor

    node = ContextNode(
        tenant_id="t1", node_type="doc", memory_type=MemoryType.SEMANTIC, content="One. Two. Three."
    )
    representation = await SimpleCompactor().compact(node, CompressionLevel.FULL)
    assert representation.tokens_saved == 0


@pytest.mark.asyncio
async def test_assemble_reports_aggregate_tokens_saved() -> None:
    os = ContextOS()
    await os.ingest(
        ContextNode(
            tenant_id="t1",
            node_type="doc",
            memory_type=MemoryType.SEMANTIC,
            title="Release notes",
            content=(
                "Release process overview. Step one is tagging. Step two is building. "
                "Step three is publishing. Step four is announcing. Step five is archiving."
            ),
            importance=0.9,
        )
    )
    package = await os.assemble(
        ContextRequest(
            tenant_id="t1", task="release process", agent="a", token_budget=6000
        )
    )
    assert package.tokens_saved > 0  # COMPACT truncates 6 sentences down to 3
    assert package.tokens_saved == sum(
        (item.node.representations[-1].tokens_saved or 0) for item in package.items
    )
