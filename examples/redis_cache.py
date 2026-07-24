"""Redis as a working-memory/cache layer in front of a persisted store.

Requires: pip install -e ".[redis]"
And a running Redis, e.g.:

    docker run -d --name contextos-redis -p 6379:6379 redis:7-alpine

(or `docker compose up redis`, using the service in docker-compose.yml)

Redis isn't a second source of truth here -- it's a TTL read-through cache in front
of any FullContextStore (SQLiteContextStore below; swap in PostgresContextStore in
production). It caches `get_node()` specifically: `ContextOS.assemble()` itself never
calls get_node() (it works off search()/neighbors(), which the cache intentionally
passes through uncached, since their results depend on the whole query). What
benefits from the cache is the common follow-up pattern -- an agent, or a UI detail
view, repeatedly fetching a *specific* node by id after getting it back from a search
or an assembled package.

This example wraps the primary store with a call-counting subclass so the cache
hit/miss behavior is directly visible, not just asserted in a test.
"""

import asyncio
import os
import tempfile
from pathlib import Path
from uuid import UUID

import redis.asyncio as redis

from contextos import ContextNode, MemoryType
from contextos.models import ContextNode as ContextNodeModel
from contextos.storage.redis_cache import RedisCachedContextStore
from contextos.storage.sqlite import SQLiteContextStore

REDIS_URL = os.environ.get("CONTEXTOS_REDIS_URL", "redis://localhost:6379/0")


class CountingSQLiteStore(SQLiteContextStore):
    """SQLiteContextStore that counts get_node() calls, to make the cache's effect
    on primary-store load visible rather than just asserted."""

    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self.get_node_calls = 0

    async def get_node(self, tenant_id: str, node_id: UUID) -> ContextNodeModel | None:
        self.get_node_calls += 1
        return await super().get_node(tenant_id, node_id)


async def main() -> None:
    redis_client = redis.from_url(REDIS_URL)
    with tempfile.TemporaryDirectory() as tmp_dir:
        primary = CountingSQLiteStore(Path(tmp_dir) / "context.db")
        cached_store = RedisCachedContextStore(primary, redis_client, ttl_seconds=60)

        node = await cached_store.put_node(
            ContextNode(
                tenant_id="demo",
                node_type="project_convention",
                memory_type=MemoryType.SEMANTIC,
                title="Release convention",
                content="Stable releases use semantic versioning and include a changelog.",
                importance=0.9,
            )
        )
        print(f"after put_node(): primary store get_node() calls = {primary.get_node_calls}")

        # Simulate an agent looking the same node up repeatedly -- e.g. re-fetching
        # detail for a node it already found once via search()/assemble().
        for lookup in range(1, 4):
            fetched = await cached_store.get_node("demo", node.id)
            assert fetched is not None
            print(
                f"lookup {lookup}: primary store get_node() calls = {primary.get_node_calls} "
                f"(should stay 1 after the first lookup)"
            )

        # A write invalidates the cache -- the next read goes back to the primary store.
        node.content = "Updated: stable releases also require a migration note."
        await cached_store.put_node(node)
        await cached_store.get_node("demo", node.id)
        print(f"after update + re-fetch: primary store get_node() calls = {primary.get_node_calls}")

        primary.close()
        await redis_client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
