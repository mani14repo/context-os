"""Expose ContextOS to any MCP client (Claude Desktop, another agent, an eval harness).

Requires: pip install -e ".[mcp]"

Two ways to use this:

1. As a real stdio server, for Claude Desktop or another MCP client to connect to:

       contextos-mcp                     # in-memory store, ephemeral
       # or, for a persisted backend, write a two-line script:
       #   from contextos import ContextOS
       #   from contextos.integrations.mcp_server import build_context_server
       #   build_context_server(ContextOS(store=SQLiteContextStore("context.db"))).run()

2. Programmatically, exactly like any other ContextOS integration -- ContextOS itself
   doesn't change, `build_context_server()` just makes its ingest/search/assemble/
   link/move/history operations callable over the MCP protocol instead of only from
   Python in the same process.

This script demonstrates the second path: it connects a real MCP `ClientSession` to
the server over in-memory streams (the same mechanism the test suite uses) and calls
tools exactly as an external MCP client would, so the printed output is a real
protocol round trip, not a direct Python function call.
"""

import asyncio
import json

from mcp.shared.memory import create_connected_server_and_client_session

from contextos import ContextOS
from contextos.integrations.mcp_server import build_context_server


async def main() -> None:
    server = build_context_server(ContextOS(), name="ContextOS Demo")

    async with create_connected_server_and_client_session(server) as client:
        tools = await client.list_tools()
        print("Available tools:", [tool.name for tool in tools.tools])

        ingested = await client.call_tool(
            "ingest_context",
            {
                "tenant_id": "demo",
                "node_type": "project_convention",
                "memory_type": "semantic",
                "title": "Release convention",
                "content": "Stable releases use semantic versioning and include a changelog.",
                "importance": 0.9,
            },
        )
        print("\ningest_context ->")
        print(json.dumps(ingested.structuredContent, indent=2))

        assembled = await client.call_tool(
            "assemble_context",
            {
                "tenant_id": "demo",
                "task": "What is required for a stable release?",
                "agent": "release-assistant",
                "token_budget": 500,
            },
        )
        print("\nassemble_context ->")
        print(json.dumps(assembled.structuredContent, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
