import asyncio

from contextos import ContextEdge, ContextNode, ContextOS, ContextRequest, MemoryType


async def main() -> None:
    context_os = ContextOS()
    convention = await context_os.ingest(
        ContextNode(
            tenant_id="demo",
            node_type="project_convention",
            memory_type=MemoryType.SEMANTIC,
            title="Release convention",
            content="Stable releases use semantic versioning and include a changelog.",
            importance=0.9,
            source_authority=0.9,
        )
    )
    release_note = await context_os.ingest(
        ContextNode(
            tenant_id="demo",
            node_type="release_note",
            memory_type=MemoryType.ARTIFACT,
            title="Version 1.2 release note",
            content="Version 1.2 includes a changelog and uses semantic versioning.",
            importance=0.8,
            confidence=0.95,
        )
    )
    await context_os.link(
        ContextEdge(
            tenant_id="demo",
            source_node_id=release_note.id,
            target_node_id=convention.id,
            relationship="follows",
        )
    )
    package = await context_os.assemble(
        ContextRequest(
            tenant_id="demo",
            task="Prepare a summary of the stable release requirements",
            agent="release-assistant",
            memory_scopes={MemoryType.SEMANTIC, MemoryType.ARTIFACT},
            token_budget=500,
        )
    )
    print(package.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
