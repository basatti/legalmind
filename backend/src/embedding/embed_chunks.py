"""LEG-58 embedding pipeline for chunk-to-vector ingestion.

The pipeline is split into three pieces so the rest of the app can depend on
an interface rather than a concrete model:

1. EmbeddingProvider: turns text into a vector.
2. DocumentChunkRepository: persists the chunk metadata and embedding.
3. EmbeddingService: coordinates the flow from parsed pages to stored vectors.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod

from sqlalchemy import JSON, Column
from sqlmodel import Field, Session, SQLModel

from parsers import ParsedPage

try:
    from pgvector.sqlalchemy import Vector
except ImportError:  # pragma: no cover - optional dependency for local/test environments
    Vector = None  # type: ignore[assignment]

DEFAULT_EMBEDDING_DIMENSIONS = 16


def _embedding_column() -> Column:
    if Vector is not None:
        return Column(Vector(DEFAULT_EMBEDDING_DIMENSIONS), nullable=False)
    return Column(JSON, nullable=False)


class EmbeddingProvider(ABC):
    """Interface for turning text into a numeric vector."""

    @abstractmethod
    def embed_text(self, text: str) -> list[float]:
        """Return a vector representation of the supplied text."""


class OfflineEmbeddingProvider(EmbeddingProvider):
    """Deterministic offline embedding provider for local development and tests."""

    def __init__(self, dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        self.dimensions = dimensions

    def embed_text(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values: list[float] = []
        for index in range(self.dimensions):
            byte = digest[index % len(digest)]
            salt = digest[(index + 1) % len(digest)]
            value = ((byte ^ salt) / 255.0) * 2.0 - 1.0
            values.append(float(value))
        return values


class DocumentChunk(SQLModel, table=True):
    """One chunk of text stored alongside its vector embedding."""

    __tablename__ = "document_chunk"

    id: int | None = Field(default=None, primary_key=True)
    case_id: int
    document_id: int
    page_number: int
    sequence: int
    text: str
    embedding: list[float] = Field(sa_column=_embedding_column())


class DocumentChunkRepository:
    """Thin persistence wrapper around document chunk rows."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, chunk: DocumentChunk) -> DocumentChunk:
        self.session.add(chunk)
        return chunk

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()


class EmbeddingService:
    """Transforms parsed pages into vector rows in a single transaction."""

    def __init__(self, provider: EmbeddingProvider, repository: DocumentChunkRepository) -> None:
        self.provider = provider
        self.repository = repository

    def ingest_document(
        self,
        *,
        case_id: int,
        document_id: int,
        pages: list[ParsedPage],
    ) -> list[DocumentChunk]:
        chunks: list[DocumentChunk] = []
        try:
            for sequence, page in enumerate(pages):
                embedding = self.provider.embed_text(page.text)
                chunk = DocumentChunk(
                    case_id=case_id,
                    document_id=document_id,
                    page_number=page.page_number,
                    sequence=sequence,
                    text=page.text,
                    embedding=embedding,
                )
                chunks.append(chunk)
                self.repository.add(chunk)

            self.repository.commit()
            return chunks
        except Exception:
            self.repository.rollback()
            raise


def ingest_arabic_chunk(text_chunk: str, *, case_id: int | None = None, document_id: int | None = None) -> list[float]:
    """Backwards-compatible helper for a single chunk ingestion call."""

    provider = OfflineEmbeddingProvider()
    embedding = provider.embed_text(text_chunk)
    if case_id is None or document_id is None:
        return embedding
    return embedding
