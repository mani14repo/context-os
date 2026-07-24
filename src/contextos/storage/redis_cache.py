from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

import redis.asyncio as redis

from contextos.models import ContextEdge, ContextNode, ContextQuery, StorageTier
from contextos.protocols import FullContextStore

_DEFAULT_TTL_SECONDS = 3600  # matches the "hours to days" retention suggested for
# working/hot-tier context in the design roadmap


class RedisCachedContextStore:
    """Wraps any FullContextStore with a Redis read-through cache for get_node().

    This is the "working-memory/cache adapter" from the roadmap: Redis isn't a second
    source of truth here (that's what PostgresContextStore/SQLiteContextStore are
    for) -- it's a TTL cache in front of one, so repeated `get_node()` calls for hot
    context (the same pattern the design doc suggests Redis for) skip the primary
    store entirely until the entry expires or is invalidated.

    Only `get_node()` is cached. `search()` results depend on the whole query, not a
    single key, and aren't practical to cache generically here. `put_node()`, `move()`,
    and `delete_node()` invalidate the corresponding cache entry so callers never
    observe stale data; `put_edge()`, `neighbors()`, `record()`, and `last_accessed()`
    pass straight through to the wrapped store.
    """

    def __init__(
        self,
        store: FullContextStore,
        redis_client: redis.Redis,
        *,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
        key_prefix: str = "contextos",
    ) -> None:
        self._store = store
        self._redis = redis_client
        self._ttl_seconds = ttl_seconds
        self._key_prefix = key_prefix

    def _key(self, tenant_id: str, node_id: UUID) -> str:
        return f"{self._key_prefix}:node:{tenant_id}:{node_id}"

    async def put_node(self, node: ContextNode) -> ContextNode:
        result = await self._store.put_node(node)
        await self._redis.delete(self._key(result.tenant_id, result.id))
        return result

    async def get_node(self, tenant_id: str, node_id: UUID) -> ContextNode | None:
        key = self._key(tenant_id, node_id)
        cached = await self._redis.get(key)
        if cached is not None:
            return ContextNode.model_validate_json(cached)
        node = await self._store.get_node(tenant_id, node_id)
        if node is not None:
            await self._redis.set(key, node.model_dump_json(), ex=self._ttl_seconds)
        return node

    async def get_history(self, tenant_id: str, node_id: UUID) -> Sequence[ContextNode]:
        return await self._store.get_history(tenant_id, node_id)

    async def delete_node(self, tenant_id: str, node_id: UUID) -> bool:
        deleted = await self._store.delete_node(tenant_id, node_id)
        await self._redis.delete(self._key(tenant_id, node_id))
        return deleted

    async def search(self, query: ContextQuery) -> Sequence[ContextNode]:
        return await self._store.search(query)

    async def put_edge(self, edge: ContextEdge) -> ContextEdge:
        return await self._store.put_edge(edge)

    async def neighbors(
        self, tenant_id: str, node_ids: Sequence[UUID], depth: int = 1
    ) -> Sequence[ContextNode]:
        return await self._store.neighbors(tenant_id, node_ids, depth)

    async def edges_for_node(self, tenant_id: str, node_id: UUID) -> Sequence[ContextEdge]:
        return await self._store.edges_for_node(tenant_id, node_id)

    async def move(self, tenant_id: str, node_id: UUID, tier: StorageTier) -> ContextNode:
        result = await self._store.move(tenant_id, node_id, tier)
        await self._redis.delete(self._key(tenant_id, node_id))
        return result

    async def record(self, tenant_id: str, node_id: UUID, agent: str, task: str) -> None:
        await self._store.record(tenant_id, node_id, agent, task)

    async def last_accessed(self, tenant_id: str, node_id: UUID) -> datetime | None:
        return await self._store.last_accessed(tenant_id, node_id)
