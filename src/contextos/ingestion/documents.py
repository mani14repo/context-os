from __future__ import annotations

from pathlib import Path

from docx import Document as DocxDocument
from pypdf import PdfReader

from contextos.models import Classification, ContextNode, MemoryType

__all__ = ["DocumentExtractor"]

_SUPPORTED_SUFFIXES = {".pdf", ".docx", ".txt", ".md"}


class DocumentExtractor:
    """Extracts ContextNodes from a PDF, DOCX, or plain text/markdown file on disk.

    Splits the document's text into paragraph-grouped chunks of roughly
    `chunk_chars` characters, so a long document becomes several ContextNodes
    instead of one oversized blob -- each chunk's position is recorded in
    `metadata` (source_path, chunk_index, chunk_count) for traceability back to the
    original file. Requires `pip install -e ".[documents]"`.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        node_type: str = "document",
        memory_type: MemoryType = MemoryType.SEMANTIC,
        classification: Classification = Classification.INTERNAL,
        importance: float = 0.5,
        chunk_chars: int = 800,
    ) -> None:
        self._path = Path(path)
        suffix = self._path.suffix.lower()
        if suffix not in _SUPPORTED_SUFFIXES:
            raise ValueError(
                f"Unsupported document type {suffix!r}; expected one of {sorted(_SUPPORTED_SUFFIXES)}"
            )
        self._node_type = node_type
        self._memory_type = memory_type
        self._classification = classification
        self._importance = importance
        self._chunk_chars = chunk_chars

    def _read_text(self) -> str:
        suffix = self._path.suffix.lower()
        if suffix == ".pdf":
            reader = PdfReader(str(self._path))
            return "\n\n".join(page.extract_text() or "" for page in reader.pages)
        if suffix == ".docx":
            document = DocxDocument(str(self._path))
            return "\n\n".join(paragraph.text for paragraph in document.paragraphs)
        return self._path.read_text(encoding="utf-8")

    def _chunk(self, text: str) -> list[str]:
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        chunks: list[str] = []
        current = ""
        for paragraph in paragraphs:
            if current and len(current) + len(paragraph) + 2 > self._chunk_chars:
                chunks.append(current)
                current = paragraph
            else:
                current = f"{current}\n\n{paragraph}" if current else paragraph
        if current:
            chunks.append(current)
        return chunks or ([text.strip()] if text.strip() else [])

    async def extract(self, *, tenant_id: str) -> list[ContextNode]:
        chunks = self._chunk(self._read_text())
        multi = len(chunks) > 1
        return [
            ContextNode(
                tenant_id=tenant_id,
                node_type=self._node_type,
                memory_type=self._memory_type,
                classification=self._classification,
                title=f"{self._path.name} (part {index + 1}/{len(chunks)})" if multi else self._path.name,
                content=chunk,
                importance=self._importance,
                metadata={
                    "source_path": str(self._path),
                    "source_type": "document",
                    "chunk_index": index,
                    "chunk_count": len(chunks),
                },
            )
            for index, chunk in enumerate(chunks)
        ]
