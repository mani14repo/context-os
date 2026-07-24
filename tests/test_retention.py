from datetime import timedelta

import pytest

from contextos import ContextNode, ContextOS, MemoryType
from contextos.models import utcnow
from contextos.retention import is_eligible_for_deletion


def test_no_retention_until_is_never_eligible() -> None:
    node = ContextNode(tenant_id="t1", node_type="fact", memory_type=MemoryType.SEMANTIC)
    assert is_eligible_for_deletion(node) is False


def test_future_retention_until_is_not_eligible() -> None:
    node = ContextNode(
        tenant_id="t1",
        node_type="fact",
        memory_type=MemoryType.SEMANTIC,
        retention_until=utcnow() + timedelta(days=1),
    )
    assert is_eligible_for_deletion(node) is False


def test_past_retention_until_is_eligible() -> None:
    node = ContextNode(
        tenant_id="t1",
        node_type="fact",
        memory_type=MemoryType.SEMANTIC,
        retention_until=utcnow() - timedelta(days=1),
    )
    assert is_eligible_for_deletion(node) is True


def test_legal_hold_overrides_past_retention_until() -> None:
    node = ContextNode(
        tenant_id="t1",
        node_type="fact",
        memory_type=MemoryType.SEMANTIC,
        retention_until=utcnow() - timedelta(days=1),
        legal_hold=True,
    )
    assert is_eligible_for_deletion(node) is False


@pytest.mark.asyncio
async def test_apply_retention_policy_deletes_expired_nodes() -> None:
    os = ContextOS()
    expired = await os.ingest(
        ContextNode(
            tenant_id="t1",
            node_type="fact",
            memory_type=MemoryType.SEMANTIC,
            retention_until=utcnow() - timedelta(days=1),
        )
    )
    kept = await os.ingest(
        ContextNode(tenant_id="t1", node_type="fact", memory_type=MemoryType.SEMANTIC)
    )

    deleted = await os.apply_retention_policy("t1")

    assert [node.id for node in deleted] == [expired.id]
    assert await os.store.get_node("t1", expired.id) is None
    assert await os.store.get_node("t1", kept.id) is not None


@pytest.mark.asyncio
async def test_apply_retention_policy_skips_legal_hold_nodes() -> None:
    os = ContextOS()
    held = await os.ingest(
        ContextNode(
            tenant_id="t1",
            node_type="fact",
            memory_type=MemoryType.SEMANTIC,
            retention_until=utcnow() - timedelta(days=1),
            legal_hold=True,
        )
    )

    deleted = await os.apply_retention_policy("t1")

    assert deleted == []
    assert await os.store.get_node("t1", held.id) is not None
