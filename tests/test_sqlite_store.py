from datetime import timedelta

import pytest

from contextos import ContextEdge, ContextNode, ContextOS, ContextRequest, MemoryType, StorageTier
from contextos.errors import LegalHoldError
from contextos.models import ContextQuery, utcnow
from contextos.storage.sqlite import SQLiteContextStore


@pytest.mark.asyncio
async def test_data_survives_across_store_instances(tmp_path) -> None:
    db_path = tmp_path / "context.db"

    store1 = SQLiteContextStore(db_path)
    node = await store1.put_node(
        ContextNode(
            tenant_id="t1",
            node_type="fact",
            memory_type=MemoryType.SEMANTIC,
            content="Application A is owned by Infrastructure Engineering.",
        )
    )
    store1.close()

    # A fresh store instance pointed at the same file simulates a process restart.
    store2 = SQLiteContextStore(db_path)
    reloaded = await store2.get_node("t1", node.id)
    store2.close()

    assert reloaded is not None
    assert reloaded.content == node.content


@pytest.mark.asyncio
async def test_tenant_isolation(tmp_path) -> None:
    store = SQLiteContextStore(tmp_path / "context.db")
    node = await store.put_node(
        ContextNode(tenant_id="tenant-a", node_type="fact", memory_type=MemoryType.SEMANTIC)
    )
    assert await store.get_node("tenant-b", node.id) is None
    store.close()


@pytest.mark.asyncio
async def test_edges_and_neighbors(tmp_path) -> None:
    store = SQLiteContextStore(tmp_path / "context.db")
    control = await store.put_node(
        ContextNode(tenant_id="t1", node_type="control", memory_type=MemoryType.SEMANTIC)
    )
    evidence = await store.put_node(
        ContextNode(tenant_id="t1", node_type="evidence", memory_type=MemoryType.EPISODIC)
    )
    await store.put_edge(
        ContextEdge(
            tenant_id="t1",
            source_node_id=evidence.id,
            target_node_id=control.id,
            relationship="evidences",
        )
    )
    related = await store.neighbors("t1", [evidence.id], depth=1)
    assert [node.id for node in related] == [control.id]
    store.close()


@pytest.mark.asyncio
async def test_move_persists_tier_change(tmp_path) -> None:
    store = SQLiteContextStore(tmp_path / "context.db")
    node = await store.put_node(
        ContextNode(tenant_id="t1", node_type="fact", memory_type=MemoryType.SEMANTIC)
    )
    moved = await store.move("t1", node.id, StorageTier.ARCHIVE)
    assert moved.storage_tier is StorageTier.ARCHIVE
    reloaded = await store.get_node("t1", node.id)
    assert reloaded is not None
    assert reloaded.storage_tier is StorageTier.ARCHIVE
    store.close()


@pytest.mark.asyncio
async def test_search_matches_in_memory_scoring_behavior(tmp_path) -> None:
    store = SQLiteContextStore(tmp_path / "context.db")
    await store.put_node(
        ContextNode(
            tenant_id="t1",
            node_type="fact",
            memory_type=MemoryType.SEMANTIC,
            content="Kubernetes cluster upgrades require draining nodes first.",
            importance=0.5,
        )
    )
    results = await store.search(ContextQuery(tenant_id="t1", query="Kubernetes upgrade"))
    assert len(results) == 1
    store.close()


@pytest.mark.asyncio
async def test_sqlite_store_works_as_contextos_backend(tmp_path) -> None:
    store = SQLiteContextStore(tmp_path / "context.db")
    os = ContextOS(store=store)
    await os.ingest(
        ContextNode(
            tenant_id="t1",
            node_type="fact",
            memory_type=MemoryType.SEMANTIC,
            title="Release convention",
            content="Stable releases use semantic versioning and include a changelog.",
            importance=0.9,
        )
    )
    package = await os.assemble(
        ContextRequest(
            tenant_id="t1",
            task="What is required for a stable release?",
            agent="release-assistant",
            token_budget=300,
        )
    )
    assert package.items
    store.close()


@pytest.mark.asyncio
async def test_update_creates_version_and_history(tmp_path) -> None:
    store = SQLiteContextStore(tmp_path / "context.db")
    node = await store.put_node(
        ContextNode(tenant_id="t1", node_type="fact", memory_type=MemoryType.SEMANTIC, content="v1")
    )
    assert node.version == 1

    node.content = "v2"
    updated = await store.put_node(node)
    assert updated.version == 2

    history = await store.get_history("t1", node.id)
    assert len(history) == 1
    assert history[0].content == "v1"
    store.close()


@pytest.mark.asyncio
async def test_expired_node_excluded_from_search(tmp_path) -> None:
    store = SQLiteContextStore(tmp_path / "context.db")
    await store.put_node(
        ContextNode(
            tenant_id="t1",
            node_type="fact",
            memory_type=MemoryType.SEMANTIC,
            content="Kubernetes upgrade notes",
            valid_to=utcnow() - timedelta(days=1),
        )
    )
    results = await store.search(ContextQuery(tenant_id="t1", query="Kubernetes"))
    assert results == []
    store.close()


@pytest.mark.asyncio
async def test_access_log_records_and_returns_last_accessed(tmp_path) -> None:
    store = SQLiteContextStore(tmp_path / "context.db")
    node = await store.put_node(
        ContextNode(tenant_id="t1", node_type="fact", memory_type=MemoryType.SEMANTIC)
    )
    assert await store.last_accessed("t1", node.id) is None
    await store.record("t1", node.id, "test-agent", "test task")
    assert await store.last_accessed("t1", node.id) is not None
    store.close()


@pytest.mark.asyncio
async def test_edges_for_node_returns_both_directions(tmp_path) -> None:
    store = SQLiteContextStore(tmp_path / "context.db")
    a = await store.put_node(
        ContextNode(tenant_id="t1", node_type="fact", memory_type=MemoryType.SEMANTIC)
    )
    b = await store.put_node(
        ContextNode(tenant_id="t1", node_type="fact", memory_type=MemoryType.SEMANTIC)
    )
    c = await store.put_node(
        ContextNode(tenant_id="t1", node_type="fact", memory_type=MemoryType.SEMANTIC)
    )
    await store.put_edge(
        ContextEdge(tenant_id="t1", source_node_id=a.id, target_node_id=b.id, relationship="supports")
    )
    await store.put_edge(
        ContextEdge(tenant_id="t1", source_node_id=c.id, target_node_id=a.id, relationship="contradicts")
    )
    edges = await store.edges_for_node("t1", a.id)
    assert {edge.relationship for edge in edges} == {"supports", "contradicts"}
    store.close()


@pytest.mark.asyncio
async def test_delete_raises_legal_hold_error(tmp_path) -> None:
    store = SQLiteContextStore(tmp_path / "context.db")
    node = await store.put_node(
        ContextNode(
            tenant_id="t1", node_type="fact", memory_type=MemoryType.SEMANTIC, legal_hold=True
        )
    )
    with pytest.raises(LegalHoldError):
        await store.delete_node("t1", node.id)
    assert await store.get_node("t1", node.id) is not None
    store.close()
