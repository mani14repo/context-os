from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from contextos.errors import LegalHoldError
from contextos.models import ContextEdge, ContextNode, ContextQuery, StorageTier, utcnow
from contextos.search import score_node


class InMemoryContextStore:
    """Reference store for local development, tests, and embedded use."""

    def __init__(self) -> None:
        self.nodes: dict[UUID, ContextNode] = {}
        self.edges: dict[UUID, ContextEdge] = {}
        self.history: dict[UUID, list[ContextNode]] = {}
        self._access_log: list[tuple[str, UUID, str, str, datetime]] = []

    async def put_node(self, node: ContextNode) -> ContextNode:
        existing = self.nodes.get(node.id)
        if existing is not None:
            if existing.tenant_id != node.tenant_id:
                raise ValueError("Cannot change the tenant_id of an existing node")
            # Context is immutable by default: an update archives the prior version
            # instead of overwriting it, and bumps `version` on the live node.
            self.history.setdefault(node.id, []).append(existing)
            node.version = existing.version + 1
        node.updated_at = utcnow()
        self.nodes[node.id] = node.model_copy(deep=True)
        return node

    async def get_node(self, tenant_id: str, node_id: UUID) -> ContextNode | None:
        node = self.nodes.get(node_id)
        if node is None or node.tenant_id != tenant_id:
            return None
        return node.model_copy(deep=True)

    async def get_history(self, tenant_id: str, node_id: UUID) -> Sequence[ContextNode]:
        current = self.nodes.get(node_id)
        if current is None or current.tenant_id != tenant_id:
            return []
        return [version.model_copy(deep=True) for version in self.history.get(node_id, [])]

    async def record(self, tenant_id: str, node_id: UUID, agent: str, task: str) -> None:
        self._access_log.append((tenant_id, node_id, agent, task, utcnow()))

    async def last_accessed(self, tenant_id: str, node_id: UUID) -> datetime | None:
        timestamps = [
            accessed_at
            for tid, nid, _agent, _task, accessed_at in self._access_log
            if tid == tenant_id and nid == node_id
        ]
        return max(timestamps) if timestamps else None

    async def delete_node(self, tenant_id: str, node_id: UUID) -> bool:
        node = self.nodes.get(node_id)
        if node is None or node.tenant_id != tenant_id:
            return False
        if node.legal_hold:
            raise LegalHoldError(tenant_id, node_id)
        del self.nodes[node_id]
        self.history.pop(node_id, None)
        self.edges = {
            edge_id: edge
            for edge_id, edge in self.edges.items()
            if edge.source_node_id != node_id and edge.target_node_id != node_id
        }
        return True

    async def put_edge(self, edge: ContextEdge) -> ContextEdge:
        source = self.nodes.get(edge.source_node_id)
        target = self.nodes.get(edge.target_node_id)
        if source is None or target is None:
            raise ValueError("Both edge endpoints must exist")
        if source.tenant_id != edge.tenant_id or target.tenant_id != edge.tenant_id:
            raise ValueError("Cross-tenant edges are not allowed")
        self.edges[edge.id] = edge.model_copy(deep=True)
        return edge

    async def edges_for_node(self, tenant_id: str, node_id: UUID) -> Sequence[ContextEdge]:
        return [
            edge.model_copy(deep=True)
            for edge in self.edges.values()
            if edge.tenant_id == tenant_id
            and (edge.source_node_id == node_id or edge.target_node_id == node_id)
        ]

    async def search(self, query: ContextQuery) -> Sequence[ContextNode]:
        scored: list[tuple[float, ContextNode]] = []
        for node in self.nodes.values():
            score = score_node(query, node)
            if score is not None:
                scored.append((score, node.model_copy(deep=True)))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [node for _, node in scored[: query.max_results]]

    async def neighbors(
        self, tenant_id: str, node_ids: Sequence[UUID], depth: int = 1
    ) -> Sequence[ContextNode]:
        if depth <= 0:
            return []
        now = utcnow()
        visited = set(node_ids)
        queue = deque((node_id, 0) for node_id in node_ids)
        output: list[ContextNode] = []
        while queue:
            current, current_depth = queue.popleft()
            if current_depth >= depth:
                continue
            for edge in self.edges.values():
                if edge.tenant_id != tenant_id:
                    continue
                if edge.valid_to is not None and now >= edge.valid_to:
                    continue
                adjacent: UUID | None = None
                if edge.source_node_id == current:
                    adjacent = edge.target_node_id
                elif edge.target_node_id == current:
                    adjacent = edge.source_node_id
                if adjacent is None or adjacent in visited:
                    continue
                visited.add(adjacent)
                node = self.nodes.get(adjacent)
                if node is None or node.tenant_id != tenant_id:
                    continue
                if node.valid_from > now or (node.valid_to is not None and now >= node.valid_to):
                    continue
                output.append(node.model_copy(deep=True))
                queue.append((adjacent, current_depth + 1))
        return output

    async def move(self, tenant_id: str, node_id: UUID, tier: StorageTier) -> ContextNode:
        node = await self.get_node(tenant_id, node_id)
        if node is None:
            raise KeyError(node_id)
        node.storage_tier = tier
        return await self.put_node(node)
