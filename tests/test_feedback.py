import uuid

import pytest

from contextos import ContextNode, ContextOS, MemoryType


@pytest.mark.asyncio
async def test_record_feedback_increments_helpful_count() -> None:
    os = ContextOS()
    node = await os.ingest(
        ContextNode(
            tenant_id="t1", node_type="insight", memory_type=MemoryType.SEMANTIC, content="Retry with backoff."
        )
    )
    updated = await os.record_feedback("t1", node.id, helpful=True)
    assert updated.metadata["feedback_helpful_count"] == 1
    assert "feedback_harmful_count" not in updated.metadata


@pytest.mark.asyncio
async def test_record_feedback_increments_harmful_count() -> None:
    os = ContextOS()
    node = await os.ingest(
        ContextNode(
            tenant_id="t1", node_type="insight", memory_type=MemoryType.SEMANTIC, content="Retry with backoff."
        )
    )
    updated = await os.record_feedback("t1", node.id, helpful=False)
    assert updated.metadata["feedback_harmful_count"] == 1
    assert "feedback_helpful_count" not in updated.metadata


@pytest.mark.asyncio
async def test_record_feedback_accumulates_across_calls() -> None:
    os = ContextOS()
    node = await os.ingest(
        ContextNode(
            tenant_id="t1", node_type="insight", memory_type=MemoryType.SEMANTIC, content="Retry with backoff."
        )
    )
    await os.record_feedback("t1", node.id, helpful=True)
    await os.record_feedback("t1", node.id, helpful=True)
    updated = await os.record_feedback("t1", node.id, helpful=False)
    assert updated.metadata["feedback_helpful_count"] == 2
    assert updated.metadata["feedback_harmful_count"] == 1


@pytest.mark.asyncio
async def test_record_feedback_creates_a_new_version_each_call() -> None:
    os = ContextOS()
    node = await os.ingest(
        ContextNode(
            tenant_id="t1", node_type="insight", memory_type=MemoryType.SEMANTIC, content="Retry with backoff."
        )
    )
    await os.record_feedback("t1", node.id, helpful=True)
    updated = await os.record_feedback("t1", node.id, helpful=True)
    assert updated.version == 3  # v1 ingest, v2 first feedback, v3 second feedback
    history = await os.history("t1", node.id)
    assert len(history) == 2


@pytest.mark.asyncio
async def test_record_feedback_raises_for_missing_node() -> None:
    os = ContextOS()
    with pytest.raises(KeyError):
        await os.record_feedback("t1", uuid.uuid4(), helpful=True)
