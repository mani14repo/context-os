from __future__ import annotations

from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from azure.storage.blob import ContentSettings
from azure.storage.blob.aio import BlobServiceClient


class AzureBlobArtifactStore:
    """ArtifactStore backed by Azure Blob Storage (or the Azurite emulator locally).

    Requires `pip install -e ".[azure-blob]"`. Pointers are `azure://container/blob`
    strings, where `blob` is `{tenant_id}/{key}` -- see S3ArtifactStore's docstring
    for the same tenant-namespacing caveat.

    Testing against Azurite: recent azure-storage-blob SDK releases send an API
    version newer than older Azurite builds support, which 400s on every request.
    Start Azurite with `azurite-blob --blobHost 0.0.0.0 --skipApiVersionCheck` (see
    docker-compose.yml) if you hit "The API version ... is not supported by Azurite".
    """

    def __init__(self, service_client: BlobServiceClient, container: str) -> None:
        self._service_client = service_client
        self._container = container

    @classmethod
    def from_connection_string(
        cls, connection_string: str, container: str
    ) -> AzureBlobArtifactStore:
        return cls(BlobServiceClient.from_connection_string(connection_string), container)

    async def close(self) -> None:
        await self._service_client.close()

    async def ensure_container(self) -> None:
        """Create the container if it doesn't exist. Call once at startup; not
        implicit in put() to avoid a round trip on every write."""
        container_client = self._service_client.get_container_client(self._container)
        try:
            await container_client.create_container()
        except ResourceExistsError:
            pass

    async def put(
        self, tenant_id: str, key: str, data: bytes, content_type: str | None = None
    ) -> str:
        blob_name = f"{tenant_id}/{key}"
        blob_client = self._service_client.get_blob_client(self._container, blob_name)
        settings = ContentSettings(content_type=content_type) if content_type else None
        await blob_client.upload_blob(data, overwrite=True, content_settings=settings)
        return f"azure://{self._container}/{blob_name}"

    async def get(self, pointer: str) -> bytes:
        container, blob_name = self._parse(pointer)
        blob_client = self._service_client.get_blob_client(container, blob_name)
        downloader = await blob_client.download_blob()
        return await downloader.readall()

    async def delete(self, pointer: str) -> bool:
        container, blob_name = self._parse(pointer)
        blob_client = self._service_client.get_blob_client(container, blob_name)
        try:
            await blob_client.delete_blob()
        except ResourceNotFoundError:
            return False
        return True

    @staticmethod
    def _parse(pointer: str) -> tuple[str, str]:
        prefix = "azure://"
        if not pointer.startswith(prefix):
            raise ValueError(f"Not an azure:// pointer: {pointer!r}")
        container, _, blob_name = pointer[len(prefix) :].partition("/")
        return container, blob_name
