from __future__ import annotations

from uuid import UUID

from mcp.server.fastmcp import FastMCP

from contextos.library import ContextOS
from contextos.models import (
    ContextEdge,
    ContextNode,
    ContextQuery,
    ContextRequest,
    MemoryType,
    StorageTier,
)

__all__ = ["build_context_server"]


def _node_summary(node: ContextNode) -> dict[str, object]:
    return {
        "node_id": str(node.id),
        "title": node.title,
        "summary": node.summary,
        "memory_type": node.memory_type.value,
        "storage_tier": node.storage_tier.value,
        "importance": node.importance,
        "version": node.version,
    }


def build_context_server(context_os: ContextOS, name: str = "ContextOS") -> FastMCP:
    """Expose a ContextOS instance's core operations as MCP tools.

    ContextOS is agent-runtime-neutral by design (see the README's architecture
    decisions) -- this doesn't add a new capability to the library, it just makes the
    existing ContextOS/ContextRequest/ContextNode facade callable by any MCP client
    (Claude Desktop, another agent, an eval harness) over the standard protocol
    instead of only from Python code in the same process. Bring your own ContextOS
    instance (in-memory, SQLite, Postgres+pgvector, ...) -- this factory has no
    opinion on storage.
    """
    mcp = FastMCP(name)

    @mcp.tool()
    async def ingest_context(
        tenant_id: str,
        node_type: str,
        memory_type: str,
        content: str,
        title: str | None = None,
        summary: str | None = None,
        importance: float = 0.5,
        confidence: float = 1.0,
        source_authority: float = 0.5,
    ) -> dict[str, object]:
        """Ingest a new piece of context (a fact, decision, event, or artifact).
        memory_type must be one of: working, semantic, episodic, operational,
        procedural, artifact."""
        node = await context_os.ingest(
            ContextNode(
                tenant_id=tenant_id,
                node_type=node_type,
                memory_type=MemoryType(memory_type),
                title=title,
                summary=summary,
                content=content,
                importance=importance,
                confidence=confidence,
                source_authority=source_authority,
            )
        )
        return _node_summary(node)

    @mcp.tool()
    async def search_context(
        tenant_id: str,
        query: str,
        memory_types: list[str] | None = None,
        max_results: int = 20,
    ) -> list[dict[str, object]]:
        """Search stored context. Ranking is lexical token overlap unless the
        configured store implements vector similarity (e.g. PostgresContextStore)."""
        results = await context_os.search(
            ContextQuery(
                tenant_id=tenant_id,
                query=query,
                memory_types={MemoryType(m) for m in (memory_types or [])},
                max_results=max_results,
            )
        )
        return [_node_summary(node) for node in results]

    @mcp.tool()
    async def assemble_context(
        tenant_id: str,
        task: str,
        agent: str,
        token_budget: int = 2000,
        memory_types: list[str] | None = None,
    ) -> dict[str, object]:
        """Assemble a token-budgeted context package for a task -- the primary way an
        agent should retrieve context from ContextOS, rather than raw search."""
        package = await context_os.assemble(
            ContextRequest(
                tenant_id=tenant_id,
                task=task,
                agent=agent,
                token_budget=token_budget,
                memory_scopes={MemoryType(m) for m in (memory_types or [])},
            )
        )
        items = []
        for item in package.items:
            representation = item.node.representations[-1] if item.node.representations else None
            content = representation.content if representation else (item.node.summary or item.node.title)
            items.append({"node_id": str(item.node.id), "score": item.score, "content": content})
        return {
            "items": items,
            "token_count": package.token_count,
            "missing_context": package.missing_context,
        }

    @mcp.tool()
    async def link_context(
        tenant_id: str, source_node_id: str, target_node_id: str, relationship: str
    ) -> dict[str, object]:
        """Create a typed relationship edge between two context nodes, e.g.
        'supports', 'contradicts', 'supersedes', 'derived_from'."""
        edge = await context_os.link(
            ContextEdge(
                tenant_id=tenant_id,
                source_node_id=UUID(source_node_id),
                target_node_id=UUID(target_node_id),
                relationship=relationship,
            )
        )
        return {"edge_id": str(edge.id), "relationship": edge.relationship}

    @mcp.tool()
    async def move_context(tenant_id: str, node_id: str, tier: str) -> dict[str, object]:
        """Move a context node to a different storage tier: hot, warm, cold, or archive."""
        node = await context_os.move(tenant_id, UUID(node_id), StorageTier(tier))
        return _node_summary(node)

    @mcp.tool()
    async def context_history(tenant_id: str, node_id: str) -> list[dict[str, object]]:
        """Retrieve prior versions of a context node, oldest first."""
        history = await context_os.history(tenant_id, UUID(node_id))
        return [_node_summary(node) for node in history]

    return mcp


def main() -> None:
    """Entry point for the `contextos-mcp` console script: runs an MCP server over
    stdio backed by a fresh in-memory ContextOS. For a persisted backend, call
    build_context_server() directly with your own ContextOS instance instead."""
    build_context_server(ContextOS()).run()
