from __future__ import annotations

import math
import zlib

from contextos.text import tokenize_counts


class HashingEmbeddingProvider:
    """Deterministic, dependency-free EmbeddingProvider.

    Hashes term frequencies into a fixed-size vector (a "hashing vectorizer") and
    L2-normalizes it. This is a structural stand-in for a real embedding model, not a
    semantic one: it captures lexical overlap (shared words), not meaning -- two
    sentences about the same topic using different vocabulary will NOT be close in
    this space. It exists so PostgresContextStore's pgvector integration (storage,
    indexing, cosine-distance ranking) is fully exercised without requiring an API key
    or a heavy ML dependency. Swap in a real provider (OpenAI, Cohere,
    sentence-transformers, ...) implementing the same `embed()` method for actual
    semantic search -- see contextos.protocols.EmbeddingProvider.

    Uses zlib.crc32 rather than Python's built-in `hash()`: str hashing is randomized
    per-process by default (PYTHONHASHSEED), which would make embeddings computed in
    one process not match embeddings computed for the same text in another -- fatal
    for anything persisted, like PostgresContextStore.
    """

    def __init__(self, dimensions: int = 256) -> None:
        self.dimensions = dimensions

    async def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for term, count in tokenize_counts(text).items():
            index = zlib.crc32(term.encode("utf-8")) % self.dimensions
            vector[index] += float(count)
        magnitude = math.sqrt(sum(component * component for component in vector))
        if magnitude == 0.0:
            return vector
        return [component / magnitude for component in vector]
