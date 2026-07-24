from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

import asyncpg
from pgvector.asyncpg import register_vector

from contextos.errors import LegalHoldError
from contextos.models import ContextEdge, ContextNode, ContextQuery, StorageTier, utcnow
from contextos.protocols import EmbeddingProvider
from contextos.search import node_haystack, passes_filters


def _schema_sql(dimensions: int) -> str:
    return f"""
    CREATE TABLE IF NOT EXISTS nodes (
        id UUID PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        data JSONB NOT NULL,
        embedding vector({dimensions})
    );
    CREATE INDEX IF NOT EXISTS idx_nodes_tenant ON nodes (tenant_id);
    CREATE INDEX IF NOT EXISTS idx_nodes_embedding ON nodes
        USING hnsw (embedding vector_cosine_ops);

    CREATE TABLE IF NOT EXISTS node_history (
        node_id UUID NOT NULL,
        tenant_id TEXT NOT NULL,
        version INTEGER NOT NULL,
        data JSONB NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_history_node ON node_history (node_id);

    CREATE TABLE IF NOT EXISTS edges (
        id UUID PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        source_node_id UUID NOT NULL,
        target_node_id UUID NOT NULL,
        data JSONB NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_edges_tenant ON edges (tenant_id);
    CREATE INDEX IF NOT EXISTS idx_edges_source ON edges (source_node_id);
    CREATE INDEX IF NOT EXISTS idx_edges_target ON edges (target_node_id);

    CREATE TABLE IF NOT EXISTS access_log (
        tenant_id TEXT NOT NULL,
        node_id UUID NOT NULL,
        agent TEXT NOT NULL,
        task TEXT NOT NULL,
        accessed_at TIMESTAMPTZ NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_access_log_node ON access_log (tenant_id, node_id);
    """


class PostgresContextStore:
    """Persisted ContextStore/GraphStore/TierManager/AccessLog backed by PostgreSQL +
    pgvector, with real vector similarity search (not lexical token overlap).

    Requires `pip install -e ".[postgres]"`. Create with `PostgresContextStore.connect()`
    rather than the constructor directly -- schema setup (including the `vector`
    extension) needs to run before the connection pool registers the pgvector codec.
    Relevance ranking comes from cosine distance between the query's embedding and
    each node's stored embedding, computed by whatever `EmbeddingProvider` you pass in
    (see contextos.embeddings.HashingEmbeddingProvider for a dependency-free default,
    or contextos.protocols.EmbeddingProvider to plug in a real model).

    `dimensions` is fixed at table-creation time (`CREATE TABLE IF NOT EXISTS`, like
    any Postgres schema): connecting with a different `dimensions` against an existing
    database does not migrate the column and will raise on the first write. Changing
    embedding providers/dimensions after data exists needs an explicit migration.
    """

    def __init__(self, pool: asyncpg.Pool, embeddings: EmbeddingProvider, dimensions: int) -> None:
        self._pool = pool
        self._embeddings = embeddings
        self._dimensions = dimensions

    @classmethod
    async def connect(
        cls, dsn: str, embeddings: EmbeddingProvider, *, dimensions: int = 256
    ) -> PostgresContextStore:
        bootstrap = await asyncpg.connect(dsn)
        try:
            await bootstrap.execute("CREATE EXTENSION IF NOT EXISTS vector")
            await bootstrap.execute(_schema_sql(dimensions))
        finally:
            await bootstrap.close()
        pool = await asyncpg.create_pool(dsn, init=register_vector)
        return cls(pool, embeddings, dimensions)

    async def close(self) -> None:
        await self._pool.close()

    async def put_node(self, node: ContextNode) -> ContextNode:
        embedding = await self._embeddings.embed(node_haystack(node) or node.node_type)
        async with self._pool.acquire() as conn, conn.transaction():
            existing_row = await conn.fetchrow(
                "SELECT tenant_id, data FROM nodes WHERE id = $1", node.id
            )
            if existing_row is not None:
                if existing_row["tenant_id"] != node.tenant_id:
                    raise ValueError("Cannot change the tenant_id of an existing node")
                existing = ContextNode.model_validate_json(existing_row["data"])
                # Context is immutable by default: an update archives the prior
                # version instead of overwriting it, and bumps `version`.
                await conn.execute(
                    "INSERT INTO node_history (node_id, tenant_id, version, data) "
                    "VALUES ($1, $2, $3, $4)",
                    node.id,
                    existing.tenant_id,
                    existing.version,
                    existing.model_dump_json(),
                )
                node.version = existing.version + 1
            node.updated_at = utcnow()
            await conn.execute(
                """
                INSERT INTO nodes (id, tenant_id, data, embedding) VALUES ($1, $2, $3, $4)
                ON CONFLICT (id) DO UPDATE SET
                    tenant_id = EXCLUDED.tenant_id, data = EXCLUDED.data,
                    embedding = EXCLUDED.embedding
                """,
                node.id,
                node.tenant_id,
                node.model_dump_json(),
                embedding,
            )
        return node

    async def get_node(self, tenant_id: str, node_id: UUID) -> ContextNode | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT data FROM nodes WHERE id = $1 AND tenant_id = $2", node_id, tenant_id
            )
        return ContextNode.model_validate_json(row["data"]) if row else None

    async def get_history(self, tenant_id: str, node_id: UUID) -> Sequence[ContextNode]:
        async with self._pool.acquire() as conn:
            current = await conn.fetchrow("SELECT tenant_id FROM nodes WHERE id = $1", node_id)
            if current is None or current["tenant_id"] != tenant_id:
                return []
            rows = await conn.fetch(
                "SELECT data FROM node_history WHERE node_id = $1 AND tenant_id = $2 "
                "ORDER BY version",
                node_id,
                tenant_id,
            )
        return [ContextNode.model_validate_json(row["data"]) for row in rows]

    async def record(self, tenant_id: str, node_id: UUID, agent: str, task: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO access_log (tenant_id, node_id, agent, task, accessed_at) "
                "VALUES ($1, $2, $3, $4, $5)",
                tenant_id,
                node_id,
                agent,
                task,
                utcnow(),
            )

    async def last_accessed(self, tenant_id: str, node_id: UUID) -> datetime | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT MAX(accessed_at) AS ts FROM access_log WHERE tenant_id = $1 "
                "AND node_id = $2",
                tenant_id,
                node_id,
            )
        return row["ts"] if row else None

    async def delete_node(self, tenant_id: str, node_id: UUID) -> bool:
        existing = await self.get_node(tenant_id, node_id)
        if existing is not None and existing.legal_hold:
            raise LegalHoldError(tenant_id, node_id)
        async with self._pool.acquire() as conn, conn.transaction():
            result = await conn.execute(
                "DELETE FROM nodes WHERE id = $1 AND tenant_id = $2", node_id, tenant_id
            )
            await conn.execute(
                "DELETE FROM node_history WHERE node_id = $1 AND tenant_id = $2",
                node_id,
                tenant_id,
            )
            await conn.execute(
                "DELETE FROM edges WHERE tenant_id = $1 "
                "AND (source_node_id = $2 OR target_node_id = $2)",
                tenant_id,
                node_id,
            )
        return int(result.split()[-1]) > 0

    async def put_edge(self, edge: ContextEdge) -> ContextEdge:
        async with self._pool.acquire() as conn:
            source = await conn.fetchrow(
                "SELECT 1 FROM nodes WHERE id = $1 AND tenant_id = $2",
                edge.source_node_id,
                edge.tenant_id,
            )
            target = await conn.fetchrow(
                "SELECT 1 FROM nodes WHERE id = $1 AND tenant_id = $2",
                edge.target_node_id,
                edge.tenant_id,
            )
            if source is None or target is None:
                raise ValueError("Both edge endpoints must exist")
            await conn.execute(
                """
                INSERT INTO edges (id, tenant_id, source_node_id, target_node_id, data)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data
                """,
                edge.id,
                edge.tenant_id,
                edge.source_node_id,
                edge.target_node_id,
                edge.model_dump_json(),
            )
        return edge

    async def edges_for_node(self, tenant_id: str, node_id: UUID) -> Sequence[ContextEdge]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT data FROM edges WHERE tenant_id = $1 "
                "AND (source_node_id = $2 OR target_node_id = $2)",
                tenant_id,
                node_id,
            )
        return [ContextEdge.model_validate_json(row["data"]) for row in rows]

    async def search(self, query: ContextQuery) -> Sequence[ContextNode]:
        fetch_limit = min(max(query.max_results * 4, query.max_results), 500)
        async with self._pool.acquire() as conn:
            if query.query.strip():
                query_embedding = await self._embeddings.embed(query.query)
                rows = await conn.fetch(
                    "SELECT data FROM nodes WHERE tenant_id = $1 "
                    "ORDER BY embedding <=> $2 LIMIT $3",
                    query.tenant_id,
                    query_embedding,
                    fetch_limit,
                )
            else:
                # A blank query (e.g. ContextOS.apply_tiering_policy's "list everything"
                # query) has no meaningful direction to rank by, and pgvector's cosine
                # distance is undefined against an all-zero embedding -- skip ordering.
                rows = await conn.fetch(
                    "SELECT data FROM nodes WHERE tenant_id = $1 LIMIT $2",
                    query.tenant_id,
                    fetch_limit,
                )
        results = []
        for row in rows:
            node = ContextNode.model_validate_json(row["data"])
            if passes_filters(query, node):
                results.append(node)
        return results[: query.max_results]

    async def neighbors(
        self, tenant_id: str, node_ids: Sequence[UUID], depth: int = 1
    ) -> Sequence[ContextNode]:
        if depth <= 0:
            return []
        now = utcnow()
        visited = set(node_ids)
        queue: deque[tuple[UUID, int]] = deque((node_id, 0) for node_id in node_ids)
        output: list[ContextNode] = []
        async with self._pool.acquire() as conn:
            while queue:
                current, current_depth = queue.popleft()
                if current_depth >= depth:
                    continue
                rows = await conn.fetch(
                    "SELECT source_node_id, target_node_id, data FROM edges "
                    "WHERE tenant_id = $1 AND (source_node_id = $2 OR target_node_id = $2)",
                    tenant_id,
                    current,
                )
                for row in rows:
                    edge = ContextEdge.model_validate_json(row["data"])
                    if edge.valid_to is not None and now >= edge.valid_to:
                        continue
                    adjacent = (
                        row["target_node_id"]
                        if row["source_node_id"] == current
                        else row["source_node_id"]
                    )
                    if adjacent in visited:
                        continue
                    visited.add(adjacent)
                    node_row = await conn.fetchrow(
                        "SELECT data FROM nodes WHERE id = $1 AND tenant_id = $2",
                        adjacent,
                        tenant_id,
                    )
                    if node_row is None:
                        continue
                    node = ContextNode.model_validate_json(node_row["data"])
                    if node.valid_from > now or (
                        node.valid_to is not None and now >= node.valid_to
                    ):
                        continue
                    output.append(node)
                    queue.append((adjacent, current_depth + 1))
        return output

    async def move(self, tenant_id: str, node_id: UUID, tier: StorageTier) -> ContextNode:
        node = await self.get_node(tenant_id, node_id)
        if node is None:
            raise KeyError(node_id)
        node.storage_tier = tier
        return await self.put_node(node)
