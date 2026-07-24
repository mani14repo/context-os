import pytest

from contextos import ContextEdge, ContextNode, ContextOS, MemoryType
from contextos.models import ContextQuery
from contextos.workflows import contradictions_for, supersede


@pytest.mark.asyncio
async def test_supersede_creates_edge_and_ends_old_node_validity() -> None:
    os = ContextOS()
    old = await os.ingest(
        ContextNode(
            tenant_id="t1",
            node_type="fact",
            memory_type=MemoryType.SEMANTIC,
            content="Retention period is 30 days.",
        )
    )
    new = await os.ingest(
        ContextNode(
            tenant_id="t1",
            node_type="fact",
            memory_type=MemoryType.SEMANTIC,
            content="Retention period is 90 days.",
        )
    )

    edge = await supersede(os, "t1", new_node_id=new.id, old_node_id=old.id)

    assert edge.relationship == "supersedes"
    assert edge.source_node_id == new.id
    assert edge.target_node_id == old.id

    reloaded_old = await os.store.get_node("t1", old.id)
    assert reloaded_old is not None
    assert reloaded_old.valid_to is not None


@pytest.mark.asyncio
async def test_superseded_node_drops_out_of_search() -> None:
    os = ContextOS()
    old = await os.ingest(
        ContextNode(
            tenant_id="t1",
            node_type="fact",
            memory_type=MemoryType.SEMANTIC,
            content="Retention period is 30 days.",
        )
    )
    new = await os.ingest(
        ContextNode(
            tenant_id="t1",
            node_type="fact",
            memory_type=MemoryType.SEMANTIC,
            content="Retention period is 90 days.",
        )
    )
    await supersede(os, "t1", new_node_id=new.id, old_node_id=old.id)

    results = await os.search(ContextQuery(tenant_id="t1", query="retention period"))
    result_ids = {node.id for node in results}
    assert new.id in result_ids
    assert old.id not in result_ids


@pytest.mark.asyncio
async def test_superseded_node_history_and_id_are_preserved() -> None:
    os = ContextOS()
    old = await os.ingest(
        ContextNode(tenant_id="t1", node_type="fact", memory_type=MemoryType.SEMANTIC, content="v1")
    )
    new = await os.ingest(
        ContextNode(tenant_id="t1", node_type="fact", memory_type=MemoryType.SEMANTIC, content="v2")
    )
    await supersede(os, "t1", new_node_id=new.id, old_node_id=old.id)

    # supersede() is not delete_node(): the old node still exists, just expired.
    reloaded = await os.store.get_node("t1", old.id)
    assert reloaded is not None
    assert reloaded.content == "v1"


@pytest.mark.asyncio
async def test_contradictions_for_finds_bidirectional_matches() -> None:
    os = ContextOS()
    a = await os.ingest(
        ContextNode(tenant_id="t1", node_type="fact", memory_type=MemoryType.SEMANTIC, content="claim A")
    )
    b = await os.ingest(
        ContextNode(tenant_id="t1", node_type="fact", memory_type=MemoryType.SEMANTIC, content="claim B")
    )
    await os.link(
        ContextEdge(tenant_id="t1", source_node_id=a.id, target_node_id=b.id, relationship="contradicts")
    )

    from_a = await contradictions_for(os, "t1", a.id)
    from_b = await contradictions_for(os, "t1", b.id)
    assert [node.id for node in from_a] == [b.id]
    assert [node.id for node in from_b] == [a.id]


@pytest.mark.asyncio
async def test_contradictions_for_ignores_other_relationship_types() -> None:
    os = ContextOS()
    a = await os.ingest(
        ContextNode(tenant_id="t1", node_type="fact", memory_type=MemoryType.SEMANTIC)
    )
    b = await os.ingest(
        ContextNode(tenant_id="t1", node_type="fact", memory_type=MemoryType.SEMANTIC)
    )
    await os.link(
        ContextEdge(tenant_id="t1", source_node_id=a.id, target_node_id=b.id, relationship="supports")
    )
    assert await contradictions_for(os, "t1", a.id) == []
