import pytest
from sqlmodel import select

from embedding import (
    DocumentChunk,
    DocumentChunkRepository,
    EmbeddingProvider,
    EmbeddingService,
    OfflineEmbeddingProvider,
)
from parsers import ParsedPage


class FailingEmbeddingProvider(EmbeddingProvider):
    def embed_text(self, text: str) -> list[float]:
        if "second" in text.lower():
            raise RuntimeError("embedding failed")
        return [0.0, 1.0]


def test_offline_provider_returns_stable_fixed_size_vectors() -> None:
    provider = OfflineEmbeddingProvider(dimensions=16)

    first = provider.embed_text("This is a contract clause")
    second = provider.embed_text("This is a contract clause")

    assert first == second
    assert len(first) == 16
    assert all(isinstance(value, float) for value in first)


def test_embedding_service_persists_chunks_with_case_and_document_tags(session) -> None:
    provider = OfflineEmbeddingProvider(dimensions=16)
    repository = DocumentChunkRepository(session)
    service = EmbeddingService(provider, repository)

    pages = [
        ParsedPage(page_number=1, text="First page text"),
        ParsedPage(page_number=2, text="Second page text"),
    ]

    chunks = service.ingest_document(case_id=77, document_id=88, pages=pages)

    assert len(chunks) == 2
    assert chunks[0].case_id == 77
    assert chunks[0].document_id == 88
    assert chunks[0].page_number == 1
    assert chunks[0].sequence == 0
    assert len(chunks[0].embedding) == 16

    stored = session.exec(select(DocumentChunk).where(DocumentChunk.document_id == 88)).all()
    assert len(stored) == 2


def test_embedding_service_rolls_back_when_embedding_fails(session) -> None:
    repository = DocumentChunkRepository(session)
    service = EmbeddingService(FailingEmbeddingProvider(), repository)

    pages = [ParsedPage(page_number=1, text="First page text"), ParsedPage(page_number=2, text="Second page text")]

    with pytest.raises(RuntimeError, match="embedding failed"):
        service.ingest_document(case_id=12, document_id=34, pages=pages)

    stored = session.exec(select(DocumentChunk).where(DocumentChunk.document_id == 34)).all()
    assert stored == []
