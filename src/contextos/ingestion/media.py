from __future__ import annotations

import mimetypes
from pathlib import Path

from contextos.models import Classification, ContextNode, MemoryType
from contextos.protocols import ArtifactStore

__all__ = ["MediaExtractor"]


class MediaExtractor:
    """Stores a binary file's content via an ArtifactStore and returns a
    ContextNode carrying a `content_pointer` to it, rather than the raw bytes
    inline -- the "graph-content separation" design principle applied to
    ingestion. No text extraction is attempted (no OCR, no audio transcription):
    this connector is for opaque binary content (images, audio, video, archives)
    that should live in blob storage with just enough metadata to find and
    describe it later. For content with meaningfully extractable text, use
    DocumentExtractor instead.

    Works with any ArtifactStore implementation -- S3ArtifactStore
    (`pip install -e ".[s3]"`) or AzureBlobArtifactStore
    (`pip install -e ".[azure-blob]"`).
    """

    def __init__(
        self,
        path: str | Path,
        artifacts: ArtifactStore,
        *,
        key: str | None = None,
        content_type: str | None = None,
        node_type: str = "media",
        memory_type: MemoryType = MemoryType.ARTIFACT,
        classification: Classification = Classification.INTERNAL,
        importance: float = 0.5,
    ) -> None:
        self._path = Path(path)
        self._artifacts = artifacts
        self._key = key or self._path.name
        self._content_type = content_type or mimetypes.guess_type(self._path.name)[0]
        self._node_type = node_type
        self._memory_type = memory_type
        self._classification = classification
        self._importance = importance

    async def extract(self, *, tenant_id: str) -> list[ContextNode]:
        data = self._path.read_bytes()
        pointer = await self._artifacts.put(tenant_id, self._key, data, self._content_type)
        return [
            ContextNode(
                tenant_id=tenant_id,
                node_type=self._node_type,
                memory_type=self._memory_type,
                classification=self._classification,
                title=self._path.name,
                content_pointer=pointer,
                importance=self._importance,
                metadata={
                    "source_type": "media",
                    "filename": self._path.name,
                    "content_type": self._content_type,
                    "size_bytes": len(data),
                },
            )
        ]
