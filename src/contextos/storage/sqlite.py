from __future__ import annotations

import sqlite3
from collections import deque
from collections.abc import Sequence
from pathlib import Path
from uuid import UUID

from contextos.models import ContextEdge, ContextNode, ContextQuery, StorageTier, utcnow
from contextos.search import score_node

_SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_nodes_tenant ON nodes (tenant_id);

CREATE TABLE IF NOT EXISTS edges (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    source_node_id TEXT NOT NULL,
    target_node_id TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_edges_tenant ON edges (tenant_id);
CREATE INDEX IF NOT EXISTS idx_edges_source ON edges (source_node_id);
CREATE INDEX IF NOT EXISTS idx_edges_target ON edges (target_node_id);
"""


class SQLiteContextStore:
    """Persisted ContextStore/GraphStore/TierManager backed by stdlib `sqlite3`.

    Data survives process restarts, unlike InMemoryContextStore. It implements the
    same protocols (contextos.protocols.ContextStore/GraphStore/TierManager), so it's
    a drop-in replacement -- see examples/replaceable_infrastructure.py. The database
    calls are synchronous under the hood; that's appropriate for local/single-process
    persistence. A production adapter for a networked database (e.g. PostgreSQL, see
    the README roadmap) would use a real async driver instead.
    """

    def __init__(self, path: str | Path) -> None:
        self._conn = sqlite3.connect(str(path))
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    async def put_node(self, node: ContextNode) -> ContextNode:
        node.updated_at = utcnow()
        self._conn.execute(
            "INSERT OR REPLACE INTO nodes (id, tenant_id, data) VALUES (?, ?, ?)",
            (str(node.id), node.tenant_id, node.model_dump_json()),
        )
        self._conn.commit()
        return node

    async def get_node(self, tenant_id: str, node_id: UUID) -> ContextNode | None:
        row = self._conn.execute(
            "SELECT data FROM nodes WHERE id = ? AND tenant_id = ?",
            (str(node_id), tenant_id),
        ).fetchone()
        return ContextNode.model_validate_json(row[0]) if row else None

    async def delete_node(self, tenant_id: str, node_id: UUID) -> bool:
        cursor = self._conn.execute(
            "DELETE FROM nodes WHERE id = ? AND tenant_id = ?",
            (str(node_id), tenant_id),
        )
        self._conn.execute(
            "DELETE FROM edges WHERE tenant_id = ? AND (source_node_id = ? OR target_node_id = ?)",
            (tenant_id, str(node_id), str(node_id)),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    async def put_edge(self, edge: ContextEdge) -> ContextEdge:
        source = await self.get_node(edge.tenant_id, edge.source_node_id)
        target = await self.get_node(edge.tenant_id, edge.target_node_id)
        if source is None or target is None:
            raise ValueError("Both edge endpoints must exist")
        self._conn.execute(
            "INSERT OR REPLACE INTO edges "
            "(id, tenant_id, source_node_id, target_node_id, data) VALUES (?, ?, ?, ?, ?)",
            (
                str(edge.id),
                edge.tenant_id,
                str(edge.source_node_id),
                str(edge.target_node_id),
                edge.model_dump_json(),
            ),
        )
        self._conn.commit()
        return edge

    async def search(self, query: ContextQuery) -> Sequence[ContextNode]:
        rows = self._conn.execute(
            "SELECT data FROM nodes WHERE tenant_id = ?", (query.tenant_id,)
        ).fetchall()
        scored: list[tuple[float, ContextNode]] = []
        for (data,) in rows:
            node = ContextNode.model_validate_json(data)
            score = score_node(query, node)
            if score is not None:
                scored.append((score, node))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [node for _, node in scored[: query.max_results]]

    async def neighbors(
        self, tenant_id: str, node_ids: Sequence[UUID], depth: int = 1
    ) -> Sequence[ContextNode]:
        if depth <= 0:
            return []
        visited = set(node_ids)
        queue: deque[tuple[UUID, int]] = deque((node_id, 0) for node_id in node_ids)
        output: list[ContextNode] = []
        while queue:
            current, current_depth = queue.popleft()
            if current_depth >= depth:
                continue
            rows = self._conn.execute(
                "SELECT source_node_id, target_node_id FROM edges "
                "WHERE tenant_id = ? AND (source_node_id = ? OR target_node_id = ?)",
                (tenant_id, str(current), str(current)),
            ).fetchall()
            for source_id, target_id in rows:
                adjacent = UUID(target_id) if UUID(source_id) == current else UUID(source_id)
                if adjacent in visited:
                    continue
                visited.add(adjacent)
                node = await self.get_node(tenant_id, adjacent)
                if node is not None:
                    output.append(node)
                    queue.append((adjacent, current_depth + 1))
        return output

    async def move(self, tenant_id: str, node_id: UUID, tier: StorageTier) -> ContextNode:
        node = await self.get_node(tenant_id, node_id)
        if node is None:
            raise KeyError(node_id)
        node.storage_tier = tier
        return await self.put_node(node)
