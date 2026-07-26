"""Offline embedding provider — no network, no API key, no cost.

Two jobs:

* it lets the whole ingestion pipeline run end to end during development,
  before any real model has been chosen;
* it stands in for the real provider in tests, which must not make paid,
  network-dependent calls.

What it deliberately does NOT do is capture meaning. "cat" and "kitten" hash to
completely unrelated bytes, so their vectors are unrelated too. This provider can
prove the plumbing is right — correct count, correct width, correct order — but it
can never say anything about retrieval quality. That needs a real model.
"""

import hashlib
import math

from embeddings.base import EmbeddingProvider, Vector


class OfflineEmbeddingProvider(EmbeddingProvider):
    """Deterministic hash-based embeddings, computed locally."""

    def __init__(self, dimensions: int = 16) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed(self, texts: list[str]) -> list[Vector]:
        return [self._vector_for(text) for text in texts]

    def _vector_for(self, text: str) -> Vector:
        raw = [byte / 255.0 - 0.5 for byte in self._digest(text, self._dimensions)]
        length = math.sqrt(sum(value * value for value in raw))
        if length == 0.0:
            # Vanishingly unlikely, but a zero-length vector has no direction and
            # would break cosine similarity, so fall back to a unit vector.
            return [1.0] + [0.0] * (self._dimensions - 1)
        return [value / length for value in raw]

    @staticmethod
    def _digest(text: str, size: int) -> bytes:
        """Deterministic pseudo-random bytes for this text, as many as needed."""
        out = b""
        counter = 0
        while len(out) < size:
            out += hashlib.sha256(f"{counter}:{text}".encode()).digest()
            counter += 1
        return out[:size]
