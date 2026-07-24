from __future__ import annotations

from typing import Any

import aioboto3
from botocore.exceptions import ClientError

_NOT_FOUND_CODES = {"404", "NoSuchKey"}


class S3ArtifactStore:
    """ArtifactStore backed by Amazon S3 or any S3-compatible service (MinIO, etc.).

    Requires `pip install -e ".[s3]"`. Pointers are `s3://bucket/key` strings, where
    `key` is `{tenant_id}/{key}` -- object keys are tenant-namespaced by construction,
    not by an access check, so treat the bucket as belonging to a single ContextOS
    deployment (see SECURITY.md on tenant isolation being an application concern for
    every store, not just ContextStore).
    """

    def __init__(
        self,
        session: aioboto3.Session,
        bucket: str,
        *,
        endpoint_url: str | None = None,
        **client_kwargs: object,
    ) -> None:
        self._session = session
        self._bucket = bucket
        self._endpoint_url = endpoint_url
        self._client_kwargs = client_kwargs

    def _client(self) -> Any:
        return self._session.client("s3", endpoint_url=self._endpoint_url, **self._client_kwargs)

    async def ensure_bucket(self) -> None:
        """Create the bucket if it doesn't exist. Call once at startup; not implicit
        in put() to avoid a head/create round trip on every write."""
        async with self._client() as client:
            try:
                await client.head_bucket(Bucket=self._bucket)
            except ClientError:
                await client.create_bucket(Bucket=self._bucket)

    async def put(
        self, tenant_id: str, key: str, data: bytes, content_type: str | None = None
    ) -> str:
        object_key = f"{tenant_id}/{key}"
        put_kwargs: dict[str, object] = {"Bucket": self._bucket, "Key": object_key, "Body": data}
        if content_type:
            put_kwargs["ContentType"] = content_type
        async with self._client() as client:
            await client.put_object(**put_kwargs)
        return f"s3://{self._bucket}/{object_key}"

    async def get(self, pointer: str) -> bytes:
        bucket, key = self._parse(pointer)
        async with self._client() as client:
            response = await client.get_object(Bucket=bucket, Key=key)
            async with response["Body"] as stream:
                data: bytes = await stream.read()
        return data

    async def delete(self, pointer: str) -> bool:
        bucket, key = self._parse(pointer)
        async with self._client() as client:
            try:
                await client.head_object(Bucket=bucket, Key=key)
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") in _NOT_FOUND_CODES:
                    return False
                raise
            await client.delete_object(Bucket=bucket, Key=key)
        return True

    @staticmethod
    def _parse(pointer: str) -> tuple[str, str]:
        prefix = "s3://"
        if not pointer.startswith(prefix):
            raise ValueError(f"Not an s3:// pointer: {pointer!r}")
        bucket, _, key = pointer[len(prefix) :].partition("/")
        return bucket, key
