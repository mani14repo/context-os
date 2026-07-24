import os
from uuid import uuid4

import pytest

pytest.importorskip("asyncpg")

DSN = os.environ.get("CONTEXTOS_TEST_POSTGRES_DSN")
pytestmark = pytest.mark.skipif(DSN is None, reason="CONTEXTOS_TEST_POSTGRES_DSN not set")

from contextos import (
    ContextEdge,
    ContextNode,
    ContextOS,
    ContextRequest,
    MemoryType,
    StorageTier,
)
from contextos.embeddings import HashingEmbeddingProvider
from contextos.models import ContextQuery
from contextos.storage.postgres import PostgresContextStore

_DIMENSIONS = 32


def _tenant() -> str:
    return f"test-{uuid4().hex[:8]}"


@pytest.fixture
async def store():
    assert DSN is not None
    connected = await PostgresContextStore.connect(
        DSN, HashingEmbeddingProvider(dimensions=_DIMENSIONS), dimensions=_DIMENSIONS
    )
    try:
        yield connected
    finally:
        await connected.close()


@pytest.mark.asyncio
async def test_put_and_get_node(store) -> None:
    tenant = _tenant()
    node = await store.put_node(
        ContextNode(
            tenant_id=tenant,
            node_type="fact",
            memory_type=MemoryType.SEMANTIC,
            content="Application A is owned by Infrastructure Engineering.",
        )
    )
    reloaded = await store.get_node(tenant, node.id)
    assert reloaded is not None
    assert reloaded.content == node.content


@pytest.mark.asyncio
async def test_tenant_isolation(store) -> None:
    tenant = _tenant()
    node = await store.put_node(
        ContextNode(tenant_id=tenant, node_type="fact", memory_type=MemoryType.SEMANTIC)
    )
    assert await store.get_node(f"{tenant}-other", node.id) is None


@pytest.mark.asyncio
async def test_update_creates_version_and_history(store) -> None:
    tenant = _tenant()
    node = await store.put_node(
        ContextNode(tenant_id=tenant, node_type="fact", memory_type=MemoryType.SEMANTIC, content="v1")
    )
    assert node.version == 1

    node.content = "v2"
    updated = await store.put_node(node)
    assert updated.version == 2

    history = await store.get_history(tenant, node.id)
    assert len(history) == 1
    assert history[0].content == "v1"


@pytest.mark.asyncio
async def test_vector_search_ranks_by_meaning_not_just_keywords(store) -> None:
    tenant = _tenant()
    close = await store.put_node(
        ContextNode(
            tenant_id=tenant,
            node_type="fact",
            memory_type=MemoryType.SEMANTIC,
            title="Kubernetes upgrade",
            content="Kubernetes cluster upgrades require draining nodes first.",
        )
    )
    await store.put_node(
        ContextNode(
            tenant_id=tenant,
            node_type="fact",
            memory_type=MemoryType.SEMANTIC,
            title="Coffee machine",
            content="Descale the office coffee machine every quarter.",
        )
    )
    results = await store.search(ContextQuery(tenant_id=tenant, query="Kubernetes cluster upgrade"))
    assert results
    assert results[0].id == close.id


@pytest.mark.asyncio
async def test_blank_query_lists_everything_for_tiering(store) -> None:
    tenant = _tenant()
    await store.put_node(ContextNode(tenant_id=tenant, node_type="fact", memory_type=MemoryType.SEMANTIC))
    await store.put_node(ContextNode(tenant_id=tenant, node_type="fact", memory_type=MemoryType.SEMANTIC))
    results = await store.search(ContextQuery(tenant_id=tenant, query="", max_results=50))
    assert len(results) == 2


@pytest.mark.asyncio
async def test_edges_and_neighbors(store) -> None:
    tenant = _tenant()
    control = await store.put_node(
        ContextNode(tenant_id=tenant, node_type="control", memory_type=MemoryType.SEMANTIC)
    )
    evidence = await store.put_node(
        ContextNode(tenant_id=tenant, node_type="evidence", memory_type=MemoryType.EPISODIC)
    )
    await store.put_edge(
        ContextEdge(
            tenant_id=tenant,
            source_node_id=evidence.id,
            target_node_id=control.id,
            relationship="evidences",
        )
    )
    related = await store.neighbors(tenant, [evidence.id], depth=1)
    assert [node.id for node in related] == [control.id]


@pytest.mark.asyncio
async def test_cross_tenant_edge_rejected(store) -> None:
    tenant = _tenant()
    control = await store.put_node(
        ContextNode(tenant_id=tenant, node_type="control", memory_type=MemoryType.SEMANTIC)
    )
    other = await store.put_node(
        ContextNode(tenant_id=f"{tenant}-other", node_type="x", memory_type=MemoryType.SEMANTIC)
    )
    with pytest.raises(ValueError):
        await store.put_edge(
            ContextEdge(
                tenant_id=tenant,
                source_node_id=other.id,
                target_node_id=control.id,
                relationship="evidences",
            )
        )


@pytest.mark.asyncio
async def test_move_persists_tier_change(store) -> None:
    tenant = _tenant()
    node = await store.put_node(
        ContextNode(tenant_id=tenant, node_type="fact", memory_type=MemoryType.SEMANTIC)
    )
    moved = await store.move(tenant, node.id, StorageTier.ARCHIVE)
    assert moved.storage_tier is StorageTier.ARCHIVE


@pytest.mark.asyncio
async def test_access_log_records_and_returns_last_accessed(store) -> None:
    tenant = _tenant()
    node = await store.put_node(
        ContextNode(tenant_id=tenant, node_type="fact", memory_type=MemoryType.SEMANTIC)
    )
    assert await store.last_accessed(tenant, node.id) is None
    await store.record(tenant, node.id, "test-agent", "test task")
    assert await store.last_accessed(tenant, node.id) is not None


@pytest.mark.asyncio
async def test_postgres_store_works_as_contextos_backend(store) -> None:
    tenant = _tenant()
    context_os = ContextOS(store=store)
    await context_os.ingest(
        ContextNode(
            tenant_id=tenant,
            node_type="fact",
            memory_type=MemoryType.SEMANTIC,
            title="Release convention",
            content="Stable releases use semantic versioning and include a changelog.",
            importance=0.9,
        )
    )
    package = await context_os.assemble(
        ContextRequest(
            tenant_id=tenant,
            task="What is required for a stable release?",
            agent="release-assistant",
            token_budget=300,
        )
    )
    assert package.items
