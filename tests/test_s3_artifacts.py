import os
from uuid import uuid4

import pytest

pytest.importorskip("aioboto3")

S3_ENDPOINT = os.environ.get("CONTEXTOS_TEST_S3_ENDPOINT")
pytestmark = pytest.mark.skipif(S3_ENDPOINT is None, reason="CONTEXTOS_TEST_S3_ENDPOINT not set")

import aioboto3

from contextos.storage.s3_artifacts import S3ArtifactStore

ACCESS_KEY = os.environ.get("CONTEXTOS_TEST_S3_ACCESS_KEY", "minioadmin")
SECRET_KEY = os.environ.get("CONTEXTOS_TEST_S3_SECRET_KEY", "minioadmin")


@pytest.fixture
async def store():
    session = aioboto3.Session(
        aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY, region_name="us-east-1"
    )
    s = S3ArtifactStore(session, f"contextos-test-{uuid4().hex[:8]}", endpoint_url=S3_ENDPOINT)
    await s.ensure_bucket()
    return s


@pytest.mark.asyncio
async def test_put_get_round_trip(store) -> None:
    pointer = await store.put("t1", "docs/notes.txt", b"hello world", content_type="text/plain")
    assert pointer.startswith("s3://")
    assert await store.get(pointer) == b"hello world"


@pytest.mark.asyncio
async def test_pointer_is_tenant_namespaced(store) -> None:
    pointer = await store.put("tenant-a", "shared-key.txt", b"a")
    assert "/tenant-a/" in pointer


@pytest.mark.asyncio
async def test_delete_returns_false_for_missing_and_true_once(store) -> None:
    pointer = await store.put("t1", "to-delete.txt", b"x")
    assert await store.delete(pointer) is True
    assert await store.delete(pointer) is False


@pytest.mark.asyncio
async def test_get_after_delete_raises(store) -> None:
    pointer = await store.put("t1", "gone.txt", b"x")
    await store.delete(pointer)
    with pytest.raises(Exception):  # noqa: B017 - botocore raises its own ClientError subclass
        await store.get(pointer)


@pytest.mark.asyncio
async def test_rejects_non_s3_pointer(store) -> None:
    with pytest.raises(ValueError):
        await store.get("azure://wrong/scheme")
