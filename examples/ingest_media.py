"""Ingesting a binary file into ContextOS via blob storage, not inline content.

Needs `pip install -e ".[s3]"` and a running S3-compatible service (`docker compose up minio`).

`MediaExtractor` doesn't try to extract text from binary content (no OCR, no audio
transcription) -- it uploads the file via an ArtifactStore and returns a
ContextNode carrying a `content_pointer`, the same "graph-content separation"
principle `ContextOS.store_artifact()` uses elsewhere in the library.
"""

import asyncio
import tempfile
from pathlib import Path
from uuid import uuid4

import aioboto3

from contextos import ContextOS
from contextos.ingestion.media import MediaExtractor
from contextos.storage.s3_artifacts import S3ArtifactStore


async def main() -> None:
    session = aioboto3.Session(
        aws_access_key_id="minioadmin", aws_secret_access_key="minioadmin", region_name="us-east-1"
    )
    artifacts = S3ArtifactStore(
        session, f"contextos-demo-{uuid4().hex[:8]}", endpoint_url="http://localhost:9000"
    )
    await artifacts.ensure_bucket()

    # Sharing `artifacts` with ContextOS itself means ContextOS.load_artifact() can
    # read back what MediaExtractor wrote -- the two don't have to share a store,
    # but usually should if you want to read the content back through ContextOS.
    context_os = ContextOS(artifacts=artifacts)

    original_bytes = b"\x89PNG\r\n\x1a\n" + b"pretend this is real image data" * 20
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "incident-screenshot.png"
        path.write_bytes(original_bytes)

        nodes = await context_os.ingest_source(MediaExtractor(path, artifacts), tenant_id="acme")

    node = nodes[0]
    print(f"ingest_source() stored {node.metadata['size_bytes']} bytes via blob storage:")
    print(f"  title: {node.title}")
    print(f"  content_pointer: {node.content_pointer}")
    print(f"  content_type: {node.metadata['content_type']}")

    assert node.content_pointer is not None
    retrieved = await context_os.load_artifact(node.content_pointer)
    print(f"\nload_artifact() round trip: {len(retrieved)} bytes, matches original: {retrieved == original_bytes}")


if __name__ == "__main__":
    asyncio.run(main())
