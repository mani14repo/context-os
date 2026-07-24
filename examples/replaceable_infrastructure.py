"""Swap ContextOS's storage and compaction backends without touching calling code.

ContextOS accepts four independently swappable collaborators -- store, graph,
compactor, tier_manager -- each defined as a Protocol in `contextos.protocols`.
A custom implementation only needs to match the method signatures; there is no base
class to inherit and no vendor coupling in the core package (see CONTRIBUTING.md).

This example runs the exact same ingest/assemble workflow three times: once against
the in-memory reference store, once against the persisted SQLite store, and once
against the in-memory store paired with a custom Compactor. The workflow function
never changes -- only the collaborators passed into `ContextOS(...)` do.
"""

import asyncio
import tempfile
from pathlib import Path

from contextos import CompressionLevel, ContextNode, ContextOS, ContextRequest, MemoryType
from contextos.models import ContextRepresentation
from contextos.storage.memory import InMemoryContextStore
from contextos.storage.sqlite import SQLiteContextStore


class UppercaseCompactor:
    """A trivial custom Compactor. A real implementation might call an LLM instead;
    ContextOS only requires an object with an async `compact(node, level)` method."""

    async def compact(self, node: ContextNode, level: CompressionLevel) -> ContextRepresentation:
        source = node.content or node.summary or node.title or ""
        content = source.upper()
        return ContextRepresentation(
            level=level, content=content, token_count=max(1, len(content.split()))
        )


async def run_workflow(context_os: ContextOS, label: str) -> None:
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
    package = await context_os.assemble(
        ContextRequest(
            tenant_id="demo",
            task="What is required for a stable release?",
            agent="release-assistant",
            token_budget=500,
        )
    )
    representation = package.items[0].node.representations[-1]
    print(f"[{label}] items={len(package.items)} representation={representation.content!r}")


async def main() -> None:
    # Same workflow, in-memory backend.
    await run_workflow(ContextOS(store=InMemoryContextStore()), "in-memory store")

    # Same workflow, persisted SQLite backend -- identical calling code.
    with tempfile.TemporaryDirectory() as tmp_dir:
        sqlite_store = SQLiteContextStore(Path(tmp_dir) / "context.db")
        await run_workflow(ContextOS(store=sqlite_store), "sqlite store")
        sqlite_store.close()

    # Same workflow again, this time with a custom compactor swapped in.
    await run_workflow(
        ContextOS(store=InMemoryContextStore(), compactor=UppercaseCompactor()),
        "in-memory store + custom compactor",
    )


if __name__ == "__main__":
    asyncio.run(main())
