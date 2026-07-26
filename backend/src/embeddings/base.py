"""Embedding interfaces — stage 3 of the RAG ingestion pipeline (LEG-13).

Turns chunk text into vectors. The interface exists because the real provider
is a paid, slow, network-dependent service that cannot run in tests — so a fake
implementation stands in for it (see fake.py). Nothing downstream knows or cares
which model produced a vector.

Mirrors the Parser and Chunker patterns.
"""

from abc import ABC, abstractmethod

Vector = list[float]
"""One embedding: a fixed-length list of numbers representing a piece of text."""


class EmbeddingProvider(ABC):
    """Common interface for turning text into vectors."""

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """How many numbers are in each vector.

        Fixed by the model and never varies between calls. Stage 4 needs it to
        create the pgvector column, and vectors from two different models cannot
        be compared at all — so changing model later means re-embedding every
        document, not just new ones.
        """

    @abstractmethod
    def embed(self, texts: list[str]) -> list[Vector]:
        """Embed several texts at once, returning one vector per input, in order.

        Implementations must return exactly len(texts) vectors, each of length
        self.dimensions, matching the input order — callers pair them up by
        position.
        """
