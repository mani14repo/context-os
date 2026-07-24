"""PostgreSQL + pgvector: a persisted store with real vector similarity search.

Requires: pip install -e ".[postgres]"
And a running Postgres with the pgvector extension available, e.g.:

    docker run -d --name contextos-pg -e POSTGRES_PASSWORD=contextos \\
        -e POSTGRES_DB=contextos -p 5432:5432 pgvector/pgvector:pg16

(or `docker compose up postgres`, using the service in docker-compose.yml)

Unlike InMemoryContextStore/SQLiteContextStore, which rank by lexical token overlap,
PostgresContextStore ranks by cosine distance between embedding vectors using
pgvector's `<=>` operator -- the actual mechanic a production semantic search backend
uses. This example uses HashingEmbeddingProvider (contextos.embeddings), a
dependency-free deterministic embedder that captures shared vocabulary, not deep
meaning -- it exists to exercise the pgvector storage/ranking mechanics honestly,
without requiring an API key or a heavy ML dependency. Swap in a real embedding
provider (OpenAI, Cohere, sentence-transformers, ...) that implements
`contextos.protocols.EmbeddingProvider` for actual semantic search.
"""

import asyncio
import os

from contextos import ContextNode, ContextOS, ContextRequest, MemoryType
from contextos.embeddings import HashingEmbeddingProvider
from contextos.storage.postgres import PostgresContextStore

DSN = os.environ.get("CONTEXTOS_POSTGRES_DSN", "postgresql://postgres:contextos@localhost:5432/contextos")
DIMENSIONS = 128


async def main() -> None:
    store = await PostgresContextStore.connect(
        DSN, HashingEmbeddingProvider(dimensions=DIMENSIONS), dimensions=DIMENSIONS
    )
    try:
        context_os = ContextOS(store=store)

        await context_os.ingest(
            ContextNode(
                tenant_id="demo",
                node_type="runbook",
                memory_type=MemoryType.OPERATIONAL,
                title="Kubernetes upgrade checklist",
                content="Kubernetes cluster upgrades require draining nodes before the control plane bump.",
                importance=0.8,
            )
        )
        await context_os.ingest(
            ContextNode(
                tenant_id="demo",
                node_type="fact",
                memory_type=MemoryType.SEMANTIC,
                title="Coffee machine maintenance",
                content="Descale the office coffee machine every quarter with a vinegar solution.",
                importance=0.3,
            )
        )

        package = await context_os.assemble(
            ContextRequest(
                tenant_id="demo",
                task="How do I upgrade the Kubernetes control plane?",
                agent="ops-assistant",
                token_budget=500,
            )
        )
        print(f"Ranked by pgvector cosine distance ({len(package.items)} result(s)):")
        for item in package.items:
            print(f"  score={item.score:>6}  {item.node.title}")

        # Versioning and access logging are the same PostgresContextStore behaviors
        # as every other backend -- see the "Versioning, temporal validity, access
        # logging, and tiering" section in README.md.
        node = package.items[0].node
        last_accessed = await context_os.access_log.last_accessed("demo", node.id)
        print(f"\n'{node.title}' was just accessed at: {last_accessed}")
    finally:
        await store.close()


if __name__ == "__main__":
    asyncio.run(main())
