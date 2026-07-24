from contextlib import asynccontextmanager

import pytest

pytest.importorskip("mcp")

from mcp.shared.memory import create_connected_server_and_client_session

from contextos.integrations.mcp_server import build_context_server
from contextos.library import ContextOS


@asynccontextmanager
async def connected_client():
    server = build_context_server(ContextOS())
    async with create_connected_server_and_client_session(server, raise_exceptions=True) as session:
        yield session


@pytest.mark.asyncio
async def test_lists_expected_tools() -> None:
    async with connected_client() as client:
        result = await client.list_tools()
        names = {tool.name for tool in result.tools}
        assert names == {
            "ingest_context",
            "search_context",
            "assemble_context",
            "link_context",
            "move_context",
            "context_history",
        }


@pytest.mark.asyncio
async def test_ingest_and_search_round_trip() -> None:
    async with connected_client() as client:
        ingested = await client.call_tool(
            "ingest_context",
            {
                "tenant_id": "t1",
                "node_type": "fact",
                "memory_type": "semantic",
                "content": "Kubernetes cluster upgrades require draining nodes first.",
                "title": "Kubernetes upgrade checklist",
                "importance": 0.8,
            },
        )
        assert ingested.isError is False
        node_id = ingested.structuredContent["node_id"]

        found = await client.call_tool(
            "search_context", {"tenant_id": "t1", "query": "Kubernetes upgrade"}
        )
        assert found.isError is False
        assert any(item["node_id"] == node_id for item in found.structuredContent["result"])


@pytest.mark.asyncio
async def test_assemble_returns_budgeted_package() -> None:
    async with connected_client() as client:
        await client.call_tool(
            "ingest_context",
            {
                "tenant_id": "t1",
                "node_type": "fact",
                "memory_type": "semantic",
                "content": "Stable releases use semantic versioning and include a changelog.",
                "title": "Release convention",
                "importance": 0.9,
            },
        )
        result = await client.call_tool(
            "assemble_context",
            {
                "tenant_id": "t1",
                "task": "What is required for a stable release?",
                "agent": "release-assistant",
                "token_budget": 500,
            },
        )
        assert result.isError is False
        assert result.structuredContent["items"]
        assert result.structuredContent["token_count"] > 0


@pytest.mark.asyncio
async def test_link_and_move_and_history() -> None:
    async with connected_client() as client:
        source = await client.call_tool(
            "ingest_context",
            {"tenant_id": "t1", "node_type": "evidence", "memory_type": "episodic", "content": "e"},
        )
        target = await client.call_tool(
            "ingest_context",
            {"tenant_id": "t1", "node_type": "control", "memory_type": "semantic", "content": "c"},
        )
        source_id = source.structuredContent["node_id"]
        target_id = target.structuredContent["node_id"]

        linked = await client.call_tool(
            "link_context",
            {
                "tenant_id": "t1",
                "source_node_id": source_id,
                "target_node_id": target_id,
                "relationship": "evidences",
            },
        )
        assert linked.isError is False

        moved = await client.call_tool(
            "move_context", {"tenant_id": "t1", "node_id": target_id, "tier": "archive"}
        )
        assert moved.isError is False
        assert moved.structuredContent["storage_tier"] == "archive"

        # move_context re-ingests the node (a real update), so it now has one prior version.
        history = await client.call_tool(
            "context_history", {"tenant_id": "t1", "node_id": target_id}
        )
        assert history.isError is False
        assert len(history.structuredContent["result"]) == 1


@pytest.mark.asyncio
async def test_invalid_memory_type_is_reported_as_tool_error() -> None:
    async with connected_client() as client:
        result = await client.call_tool(
            "ingest_context",
            {
                "tenant_id": "t1",
                "node_type": "fact",
                "memory_type": "not-a-real-memory-type",
                "content": "x",
            },
        )
        assert result.isError is True
