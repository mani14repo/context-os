from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from uuid import UUID

from contextos.models import ContextEdge, ContextNode, ContextQuery, StorageTier, utcnow
from contextos.search import score_node


class InMemoryContextStore:
    """Reference store for local development, tests, and embedded use."""

    def __init__(self) -> None:
        self.nodes: dict[UUID, ContextNode] = {}
        self.edges: dict[UUID, ContextEdge] = {}

    async def put_node(self, node: ContextNode) -> ContextNode:
        node.updated_at = utcnow()
        self.nodes[node.id] = node.model_copy(deep=True)
        return node

    async def get_node(self, tenant_id: str, node_id: UUID) -> ContextNode | None:
        node = self.nodes.get(node_id)
        if node is None or node.tenant_id != tenant_id:
            return None
        return node.model_copy(deep=True)

    async def delete_node(self, tenant_id: str, node_id: UUID) -> bool:
        node = self.nodes.get(node_id)
        if node is None or node.tenant_id != tenant_id:
            return False
        del self.nodes[node_id]
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
                adjacent: UUID | None = None
                if edge.source_node_id == current:
                    adjacent = edge.target_node_id
                elif edge.target_node_id == current:
                    adjacent = edge.source_node_id
                if adjacent is None or adjacent in visited:
                    continue
                visited.add(adjacent)
                node = self.nodes.get(adjacent)
                if node is not None and node.tenant_id == tenant_id:
                    output.append(node.model_copy(deep=True))
                    queue.append((adjacent, current_depth + 1))
        return output

    async def move(self, tenant_id: str, node_id: UUID, tier: StorageTier) -> ContextNode:
        node = await self.get_node(tenant_id, node_id)
        if node is None:
            raise KeyError(node_id)
        node.storage_tier = tier
        return await self.put_node(node)
