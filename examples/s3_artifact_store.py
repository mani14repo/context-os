"""S3 (or any S3-compatible service) as the object store for large/original content.

Requires: pip install -e ".[s3]"
And a running S3-compatible service, e.g. MinIO:

    docker run -d --name contextos-minio -p 9000:9000 \\
        -e MINIO_ROOT_USER=minioadmin -e MINIO_ROOT_PASSWORD=minioadmin \\
        minio/minio server /data

(or `docker compose up minio`, using the service in docker-compose.yml)

This is the "graph-content separation" design principle: a ContextNode carries a
short `content`/`summary` for retrieval and ranking, plus a `content_pointer` to the
full original artifact (a transcript, a PDF, a large log) living in object storage --
not inlined into the node itself. `ContextOS.store_artifact()`/`load_artifact()` are
the facade methods for that pointer's other end.
"""

import asyncio
import os

import aioboto3

from contextos import ContextNode, ContextOS, MemoryType
from contextos.storage.s3_artifacts import S3ArtifactStore

S3_ENDPOINT = os.environ.get("CONTEXTOS_S3_ENDPOINT", "http://localhost:9000")
ACCESS_KEY = os.environ.get("CONTEXTOS_S3_ACCESS_KEY", "minioadmin")
SECRET_KEY = os.environ.get("CONTEXTOS_S3_SECRET_KEY", "minioadmin")

ORIGINAL_TRANSCRIPT = b"""[Meeting transcript -- DR cutover retro]
00:00 Alice: Let's walk through what happened during the DR cutover test.
00:14 Bob: The Keycloak restoration step was incomplete, that's what triggered the rollback.
02:03 Alice: Agreed. Let's add an explicit readiness probe before the traffic shift next time.
"""


async def main() -> None:
    session = aioboto3.Session(
        aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY, region_name="us-east-1"
    )
    artifacts = S3ArtifactStore(session, "contextos-demo", endpoint_url=S3_ENDPOINT)
    await artifacts.ensure_bucket()

    context_os = ContextOS(artifacts=artifacts)

    pointer = await context_os.store_artifact(
        "demo", "meetings/dr-cutover-retro.txt", ORIGINAL_TRANSCRIPT, content_type="text/plain"
    )
    print(f"Original transcript stored at: {pointer}")

    node = await context_os.ingest(
        ContextNode(
            tenant_id="demo",
            node_type="meeting_transcript",
            memory_type=MemoryType.EPISODIC,
            title="DR cutover retro",
            summary="Keycloak restoration was incomplete; add a readiness probe before the next cutover.",
            content_pointer=pointer,
            importance=0.7,
        )
    )
    print(f"Node {node.id} carries only a pointer -- node.content is: {node.content!r}")

    restored = await context_os.load_artifact(node.content_pointer)
    print(f"\nFull original transcript loaded back from S3:\n{restored.decode()}")


if __name__ == "__main__":
    asyncio.run(main())
