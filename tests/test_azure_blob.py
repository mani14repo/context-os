import os
from uuid import uuid4

import pytest

pytest.importorskip("azure.storage.blob")

CONNECTION_STRING = os.environ.get("CONTEXTOS_TEST_AZURE_CONNECTION_STRING")
pytestmark = pytest.mark.skipif(
    CONNECTION_STRING is None, reason="CONTEXTOS_TEST_AZURE_CONNECTION_STRING not set"
)

from contextos.storage.azure_artifacts import AzureBlobArtifactStore


@pytest.fixture
async def store():
    assert CONNECTION_STRING is not None
    s = AzureBlobArtifactStore.from_connection_string(
        CONNECTION_STRING, f"contextos-test-{uuid4().hex[:8]}"
    )
    await s.ensure_container()
    try:
        yield s
    finally:
        await s.close()


@pytest.mark.asyncio
async def test_put_get_round_trip(store) -> None:
    pointer = await store.put("t1", "docs/notes.txt", b"hello world", content_type="text/plain")
    assert pointer.startswith("azure://")
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
async def test_rejects_non_azure_pointer(store) -> None:
    with pytest.raises(ValueError):
        await store.get("s3://wrong/scheme")
