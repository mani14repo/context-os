import pytest

from contextos import ContextNode, ContextOS, MemoryType
from contextos.provenance import build_provenance_manifest, verify_provenance_manifest


@pytest.mark.asyncio
async def test_manifest_has_one_entry_for_a_never_updated_node() -> None:
    os = ContextOS()
    node = await os.ingest(
        ContextNode(tenant_id="t1", node_type="fact", memory_type=MemoryType.SEMANTIC, content="v1")
    )
    manifest = await build_provenance_manifest(os, "t1", node.id)
    assert len(manifest.entries) == 1
    assert manifest.entries[0].version == 1


@pytest.mark.asyncio
async def test_manifest_includes_full_history_oldest_first() -> None:
    os = ContextOS()
    node = await os.ingest(
        ContextNode(tenant_id="t1", node_type="fact", memory_type=MemoryType.SEMANTIC, content="v1")
    )
    node.content = "v2"
    await os.ingest(node)
    node.content = "v3"
    await os.ingest(node)

    manifest = await build_provenance_manifest(os, "t1", node.id)
    assert [entry.version for entry in manifest.entries] == [1, 2, 3]


@pytest.mark.asyncio
async def test_manifest_is_deterministic_when_nothing_changes() -> None:
    os = ContextOS()
    node = await os.ingest(
        ContextNode(tenant_id="t1", node_type="fact", memory_type=MemoryType.SEMANTIC, content="v1")
    )
    first = await build_provenance_manifest(os, "t1", node.id)
    second = await build_provenance_manifest(os, "t1", node.id)
    assert first.manifest_hash == second.manifest_hash


@pytest.mark.asyncio
async def test_manifest_raises_for_missing_node() -> None:
    import uuid

    os = ContextOS()
    with pytest.raises(KeyError):
        await build_provenance_manifest(os, "t1", uuid.uuid4())


@pytest.mark.asyncio
async def test_verify_passes_for_untampered_history() -> None:
    os = ContextOS()
    node = await os.ingest(
        ContextNode(tenant_id="t1", node_type="fact", memory_type=MemoryType.SEMANTIC, content="v1")
    )
    node.content = "v2"
    await os.ingest(node)

    manifest = await build_provenance_manifest(os, "t1", node.id)
    assert await verify_provenance_manifest(os, manifest) is True


@pytest.mark.asyncio
async def test_verify_detects_tampering_with_archived_history() -> None:
    os = ContextOS()
    node = await os.ingest(
        ContextNode(tenant_id="t1", node_type="fact", memory_type=MemoryType.SEMANTIC, content="v1")
    )
    node.content = "v2"
    await os.ingest(node)

    manifest = await build_provenance_manifest(os, "t1", node.id)
    assert await verify_provenance_manifest(os, manifest) is True

    # Simulate tampering: mutate the archived version directly, bypassing put_node()
    # (and therefore bypassing the immutability guarantee entirely) -- this is
    # exactly the scenario a provenance manifest exists to catch.
    os.store.history[node.id][0] = os.store.history[node.id][0].model_copy(  # type: ignore[attr-defined]
        update={"content": "tampered"}
    )

    assert await verify_provenance_manifest(os, manifest) is False


@pytest.mark.asyncio
async def test_verify_detects_tampering_with_current_version() -> None:
    os = ContextOS()
    node = await os.ingest(
        ContextNode(tenant_id="t1", node_type="fact", memory_type=MemoryType.SEMANTIC, content="v1")
    )
    manifest = await build_provenance_manifest(os, "t1", node.id)

    os.store.nodes[node.id] = os.store.nodes[node.id].model_copy(  # type: ignore[attr-defined]
        update={"content": "tampered"}
    )

    assert await verify_provenance_manifest(os, manifest) is False
