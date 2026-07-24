import os
from collections.abc import Sequence
from uuid import UUID, uuid4

import pytest

pytest.importorskip("redis")

REDIS_URL = os.environ.get("CONTEXTOS_TEST_REDIS_URL")
pytestmark = pytest.mark.skipif(REDIS_URL is None, reason="CONTEXTOS_TEST_REDIS_URL not set")

import redis.asyncio as redis

from contextos import ContextNode, MemoryType, StorageTier
from contextos.storage.memory import InMemoryContextStore
from contextos.storage.redis_cache import RedisCachedContextStore


class CountingStore(InMemoryContextStore):
    """Wraps InMemoryContextStore to count get_node() calls, so tests can assert the
    Redis cache is actually skipping the primary store rather than just working by
    coincidence."""

    def __init__(self) -> None:
        super().__init__()
        self.get_node_calls = 0

    async def get_node(self, tenant_id: str, node_id: UUID) -> ContextNode | None:
        self.get_node_calls += 1
        return await super().get_node(tenant_id, node_id)


def _tenant() -> str:
    return f"test-{uuid4().hex[:8]}"


@pytest.fixture
async def redis_client():
    assert REDIS_URL is not None
    client = redis.from_url(REDIS_URL)
    try:
        yield client
    finally:
        await client.flushdb()
        await client.aclose()


@pytest.mark.asyncio
async def test_repeated_get_node_hits_cache_not_primary_store(redis_client) -> None:
    primary = CountingStore()
    cached = RedisCachedContextStore(primary, redis_client, key_prefix=uuid4().hex)
    tenant = _tenant()
    node = await cached.put_node(
        ContextNode(tenant_id=tenant, node_type="fact", memory_type=MemoryType.SEMANTIC, content="x")
    )
    assert primary.get_node_calls == 0

    first = await cached.get_node(tenant, node.id)
    second = await cached.get_node(tenant, node.id)
    third = await cached.get_node(tenant, node.id)

    assert first is not None and second is not None and third is not None
    assert first.content == second.content == third.content == "x"
    # Only the first get_node() should have missed the cache and hit the primary store.
    assert primary.get_node_calls == 1


@pytest.mark.asyncio
async def test_put_node_invalidates_cache(redis_client) -> None:
    primary = CountingStore()
    cached = RedisCachedContextStore(primary, redis_client, key_prefix=uuid4().hex)
    tenant = _tenant()
    node = await cached.put_node(
        ContextNode(tenant_id=tenant, node_type="fact", memory_type=MemoryType.SEMANTIC, content="v1")
    )
    warm = await cached.get_node(tenant, node.id)
    assert warm is not None and warm.content == "v1"

    node.content = "v2"
    await cached.put_node(node)
    reloaded = await cached.get_node(tenant, node.id)
    assert reloaded is not None
    assert reloaded.content == "v2"


@pytest.mark.asyncio
async def test_move_invalidates_cache(redis_client) -> None:
    primary = CountingStore()
    cached = RedisCachedContextStore(primary, redis_client, key_prefix=uuid4().hex)
    tenant = _tenant()
    node = await cached.put_node(
        ContextNode(tenant_id=tenant, node_type="fact", memory_type=MemoryType.SEMANTIC)
    )
    await cached.get_node(tenant, node.id)  # warm the cache at the default (WARM) tier

    await cached.move(tenant, node.id, StorageTier.ARCHIVE)
    reloaded = await cached.get_node(tenant, node.id)
    assert reloaded is not None
    assert reloaded.storage_tier is StorageTier.ARCHIVE


@pytest.mark.asyncio
async def test_delete_node_invalidates_cache(redis_client) -> None:
    primary = CountingStore()
    cached = RedisCachedContextStore(primary, redis_client, key_prefix=uuid4().hex)
    tenant = _tenant()
    node = await cached.put_node(
        ContextNode(tenant_id=tenant, node_type="fact", memory_type=MemoryType.SEMANTIC)
    )
    await cached.get_node(tenant, node.id)  # warm the cache

    assert await cached.delete_node(tenant, node.id) is True
    assert await cached.get_node(tenant, node.id) is None


@pytest.mark.asyncio
async def test_ttl_expiry_falls_back_to_primary_store(redis_client) -> None:
    primary = CountingStore()
    cached = RedisCachedContextStore(primary, redis_client, ttl_seconds=1, key_prefix=uuid4().hex)
    tenant = _tenant()
    node = await cached.put_node(
        ContextNode(tenant_id=tenant, node_type="fact", memory_type=MemoryType.SEMANTIC)
    )
    await cached.get_node(tenant, node.id)
    assert primary.get_node_calls == 1

    import asyncio

    await asyncio.sleep(1.5)
    await cached.get_node(tenant, node.id)
    assert primary.get_node_calls == 2


@pytest.mark.asyncio
async def test_search_and_neighbors_pass_through_uncached(redis_client) -> None:
    primary = CountingStore()
    cached = RedisCachedContextStore(primary, redis_client, key_prefix=uuid4().hex)
    tenant = _tenant()
    await cached.put_node(
        ContextNode(
            tenant_id=tenant,
            node_type="fact",
            memory_type=MemoryType.SEMANTIC,
            content="Kubernetes upgrade notes",
        )
    )
    from contextos.models import ContextQuery

    results: Sequence[ContextNode] = await cached.search(
        ContextQuery(tenant_id=tenant, query="Kubernetes")
    )
    assert len(results) == 1
