"""Persist context across process restarts with SQLiteContextStore.

InMemoryContextStore (the default) loses everything when the process exits -- fine
for tests and prototypes, not for a long-running agent. SQLiteContextStore is a
stdlib-only, zero-extra-dependency ContextStore/GraphStore/TierManager implementation
that writes to a real file, so context ingested in one run is still there in the next.

This example simulates two separate process runs against the same database file: the
first ingests a node, the second (a fresh SQLiteContextStore instance, standing in for
a fresh process) reads it back and assembles context from it.
"""

import asyncio
import sys
from pathlib import Path

from contextos import ContextNode, ContextOS, ContextRequest, MemoryType
from contextos.storage.sqlite import SQLiteContextStore


async def run_one(db_path: Path) -> None:
    store = SQLiteContextStore(db_path)
    context_os = ContextOS(store=store)

    package = await context_os.assemble(
        ContextRequest(
            tenant_id="demo",
            task="What is required for a stable release?",
            agent="release-assistant",
            token_budget=500,
        )
    )
    if package.items:
        print(f"Found {len(package.items)} node(s) already stored from a previous run:")
        for item in package.items:
            print(f"  - {item.node.title}")
    else:
        print("No prior context found -- ingesting it for the first time.")
        await context_os.ingest(
            ContextNode(
                tenant_id="demo",
                node_type="project_convention",
                memory_type=MemoryType.SEMANTIC,
                title="Release convention",
                content="Stable releases use semantic versioning and include a changelog.",
                importance=0.9,
            )
        )

    store.close()


async def main() -> None:
    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("contextos_demo.sqlite3")
    print(f"Using database file: {db_path.resolve()}")
    await run_one(db_path)
    print("\nRun this script again (same file) to see the context persist.")


if __name__ == "__main__":
    asyncio.run(main())
