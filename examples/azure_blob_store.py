"""Azure Blob Storage as the object store for large/original content.

Requires: pip install -e ".[azure-blob]"
And a running Azure Blob endpoint, e.g. the Azurite emulator:

    docker run -d --name contextos-azurite -p 10000:10000 \\
        mcr.microsoft.com/azure-storage/azurite \\
        azurite-blob --blobHost 0.0.0.0 --skipApiVersionCheck

(or `docker compose up azurite`, using the service in docker-compose.yml; the
--skipApiVersionCheck flag is needed because recent azure-storage-blob SDK releases
send an API version newer than older Azurite builds support)

Same "graph-content separation" story as examples/s3_artifact_store.py, backed by
Azure Blob Storage instead of S3.
"""

import asyncio
import os

from contextos import ContextNode, ContextOS, MemoryType
from contextos.storage.azure_artifacts import AzureBlobArtifactStore

CONNECTION_STRING = os.environ.get(
    "CONTEXTOS_AZURE_CONNECTION_STRING",
    "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;"
    "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;"
    "BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;",
)

ORIGINAL_TRANSCRIPT = b"""[Meeting transcript -- DR cutover retro]
00:00 Alice: Let's walk through what happened during the DR cutover test.
00:14 Bob: The Keycloak restoration step was incomplete, that's what triggered the rollback.
02:03 Alice: Agreed. Let's add an explicit readiness probe before the traffic shift next time.
"""


async def main() -> None:
    artifacts = AzureBlobArtifactStore.from_connection_string(CONNECTION_STRING, "contextos-demo")
    await artifacts.ensure_container()

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
    print(f"\nFull original transcript loaded back from Azure Blob:\n{restored.decode()}")

    await artifacts.close()


if __name__ == "__main__":
    asyncio.run(main())
