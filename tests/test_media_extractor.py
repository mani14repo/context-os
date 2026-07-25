import os
from pathlib import Path
from uuid import uuid4

import pytest

pytest.importorskip("aioboto3")

S3_ENDPOINT = os.environ.get("CONTEXTOS_TEST_S3_ENDPOINT")
pytestmark = pytest.mark.skipif(S3_ENDPOINT is None, reason="CONTEXTOS_TEST_S3_ENDPOINT not set")

import aioboto3

from contextos.ingestion.media import MediaExtractor
from contextos.storage.s3_artifacts import S3ArtifactStore

ACCESS_KEY = os.environ.get("CONTEXTOS_TEST_S3_ACCESS_KEY", "minioadmin")
SECRET_KEY = os.environ.get("CONTEXTOS_TEST_S3_SECRET_KEY", "minioadmin")


@pytest.fixture
async def artifacts() -> S3ArtifactStore:
    session = aioboto3.Session(
        aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY, region_name="us-east-1"
    )
    store = S3ArtifactStore(session, f"contextos-test-{uuid4().hex[:8]}", endpoint_url=S3_ENDPOINT)
    await store.ensure_bucket()
    return store


@pytest.mark.asyncio
async def test_stores_real_binary_content_via_artifact_store(
    tmp_path: Path, artifacts: S3ArtifactStore
) -> None:
    image_path = tmp_path / "photo.png"
    fake_png_bytes = b"\x89PNG\r\n\x1a\n" + b"not a real image but real bytes" * 10
    image_path.write_bytes(fake_png_bytes)

    nodes = await MediaExtractor(image_path, artifacts).extract(tenant_id="t1")

    assert len(nodes) == 1
    node = nodes[0]
    assert node.title == "photo.png"
    assert node.content is None
    assert node.content_pointer is not None
    assert node.content_pointer.startswith("s3://")
    assert node.metadata["filename"] == "photo.png"
    assert node.metadata["content_type"] == "image/png"
    assert node.metadata["size_bytes"] == len(fake_png_bytes)

    # The real, defining behavior: the bytes are actually retrievable from the
    # artifact store via the pointer the node carries, not just present in metadata.
    stored_bytes = await artifacts.get(node.content_pointer)
    assert stored_bytes == fake_png_bytes


@pytest.mark.asyncio
async def test_custom_key_overrides_filename(tmp_path: Path, artifacts: S3ArtifactStore) -> None:
    path = tmp_path / "data.bin"
    path.write_bytes(b"binary content")

    nodes = await MediaExtractor(path, artifacts, key="archive/data-v2.bin").extract(tenant_id="t1")

    assert "archive/data-v2.bin" in nodes[0].content_pointer


@pytest.mark.asyncio
async def test_unknown_extension_yields_no_content_type(
    tmp_path: Path, artifacts: S3ArtifactStore
) -> None:
    path = tmp_path / "mystery.xyzabc"
    path.write_bytes(b"???")

    nodes = await MediaExtractor(path, artifacts).extract(tenant_id="t1")

    assert nodes[0].metadata["content_type"] is None


@pytest.mark.asyncio
async def test_ingest_source_persists_media_node(tmp_path: Path, artifacts: S3ArtifactStore) -> None:
    from contextos import ContextOS

    path = tmp_path / "clip.mp3"
    path.write_bytes(b"fake mp3 bytes")

    context_os = ContextOS()
    nodes = await context_os.ingest_source(MediaExtractor(path, artifacts), tenant_id="t1")

    assert len(nodes) == 1
    stored = await context_os.store.get_node("t1", nodes[0].id)
    assert stored is not None
    assert stored.content_pointer == nodes[0].content_pointer
