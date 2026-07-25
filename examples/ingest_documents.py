"""Ingesting a real file straight into ContextOS via the Extractor protocol.

Needs `pip install -e ".[documents]"`.

`DocumentExtractor` reads a PDF, DOCX, or plain text/markdown file, splits it into
paragraph-grouped chunks, and returns ContextNodes -- `ContextOS.ingest_source()`
then ingests every one of them in a single call. This is the same one-liner every
other source in `contextos.ingestion` uses (APIs, databases, Kafka, Mattermost,
blob storage, GitHub Issues): construct the source-specific Extractor, hand it to
`ingest_source()`.
"""

import asyncio
import tempfile
from pathlib import Path

from contextos import ContextOS
from contextos.ingestion.documents import DocumentExtractor

RUNBOOK = """Disaster recovery overview.

The on-call engineer confirms three consecutive failed health checks before
declaring a regional incident.

Once declared, the database team promotes the standby replica and verifies
replication has fully caught up before allowing writes.

Traffic then shifts gradually via weighted DNS while error rates and latency
are watched on every downstream dashboard.
"""


async def main() -> None:
    context_os = ContextOS()

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "dr-runbook.md"
        path.write_text(RUNBOOK, encoding="utf-8")

        nodes = await context_os.ingest_source(
            DocumentExtractor(path, chunk_chars=250), tenant_id="acme"
        )

    print(f"ingest_source() produced {len(nodes)} node(s) from one file:")
    for node in nodes:
        print(f"  [{node.metadata['chunk_index']}] {node.title}: {node.content!r:.80}")

    stored = await context_os.store.get_node("acme", nodes[0].id)
    print(f"\nPersisted via the normal ContextStore -- confirmed: {stored is not None}")


if __name__ == "__main__":
    asyncio.run(main())
