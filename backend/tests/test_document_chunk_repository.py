"""Tests for storing chunks and their vectors (LEG-13, stage 4)."""

from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from embeddings import OfflineEmbeddingProvider
from foundation.models import EMBEDDING_DIMENSIONS, Case, Document, DocumentChunk, Role, User
from repositories.document_chunk_repository import DocumentChunkRepository


def make_document(session: Session) -> Document:
    """A real case + document to hang chunks off, since both are foreign keys."""
    user = User(
        email=f"chunks-{uuid4()}@example.com",
        full_name="Chunk Test",
        hashed_password="not-a-real-hash",
        role=Role.ATTORNEY,
    )
    case = Case(title="Chunk test case")
    session.add(user)
    session.add(case)
    session.commit()
    session.refresh(user)
    session.refresh(case)

    document = Document(
        case_id=case.id,
        filename="lease.pdf",
        file_path=f"{case.id}/lease.pdf",
        uploaded_by=user.id,
    )
    session.add(document)
    session.commit()
    session.refresh(document)
    return document


def make_chunks(document: Document, texts: list[str], start: int = 0) -> list[DocumentChunk]:
    """Build chunks with real vectors from the offline provider."""
    provider = OfflineEmbeddingProvider(dimensions=EMBEDDING_DIMENSIONS)
    vectors = provider.embed(texts)
    return [
        DocumentChunk(
            document_id=document.id,
            case_id=document.case_id,
            sequence=start + index,
            page_number=1,
            text=text,
            embedding=vector,
        )
        for index, (text, vector) in enumerate(zip(texts, vectors, strict=True))
    ]


# ---------------------------------------------------------------------------
# Storing
# ---------------------------------------------------------------------------


def test_add_many_stores_every_chunk(session: Session) -> None:
    document = make_document(session)
    repository = DocumentChunkRepository(session)

    repository.add_many(make_chunks(document, ["first", "second", "third"]))

    assert len(repository.get_by_document(document.id)) == 3


def test_stored_chunks_are_given_ids(session: Session) -> None:
    document = make_document(session)
    repository = DocumentChunkRepository(session)

    stored = repository.add_many(make_chunks(document, ["first", "second"]))

    assert all(chunk.id is not None for chunk in stored)


def test_the_vector_survives_the_round_trip(session: Session) -> None:
    """The whole point of stage 4 — a 1024-number vector goes to Postgres and
    comes back unchanged."""
    document = make_document(session)
    repository = DocumentChunkRepository(session)
    original = make_chunks(document, ["a lease clause about pets"])[0]
    expected = list(original.embedding)

    repository.add_many([original])
    stored = repository.get_by_document(document.id)[0]

    assert len(stored.embedding) == EMBEDDING_DIMENSIONS
    assert list(stored.embedding) == pytest.approx(expected, rel=1e-6)


# ---------------------------------------------------------------------------
# Reading back
# ---------------------------------------------------------------------------


def test_chunks_come_back_in_reading_order(session: Session) -> None:
    """Neighbour lookup in LEG-14 depends on sequence order being reliable."""
    document = make_document(session)
    repository = DocumentChunkRepository(session)
    chunks = make_chunks(document, ["zero", "one", "two", "three"])

    repository.add_many([chunks[2], chunks[0], chunks[3], chunks[1]])

    stored = repository.get_by_document(document.id)
    assert [chunk.sequence for chunk in stored] == [0, 1, 2, 3]
    assert [chunk.text for chunk in stored] == ["zero", "one", "two", "three"]


def test_chunks_can_be_found_by_case(session: Session) -> None:
    """LEG-14 filters on case_id to enforce that nobody reads another case."""
    document = make_document(session)
    repository = DocumentChunkRepository(session)

    repository.add_many(make_chunks(document, ["first", "second"]))

    assert len(repository.get_by_case(document.case_id)) == 2


def test_a_document_with_no_chunks_returns_nothing(session: Session) -> None:
    document = make_document(session)
    assert DocumentChunkRepository(session).get_by_document(document.id) == []


# ---------------------------------------------------------------------------
# Deleting and replacing — what re-ingestion needs
# ---------------------------------------------------------------------------


def test_delete_removes_the_chunks_and_reports_how_many(session: Session) -> None:
    document = make_document(session)
    repository = DocumentChunkRepository(session)
    repository.add_many(make_chunks(document, ["first", "second", "third"]))

    removed = repository.delete_by_document(document.id)

    assert removed == 3
    assert repository.get_by_document(document.id) == []


def test_delete_leaves_other_documents_untouched(session: Session) -> None:
    keep = make_document(session)
    remove = make_document(session)
    repository = DocumentChunkRepository(session)
    repository.add_many(make_chunks(keep, ["keep me"]))
    repository.add_many(make_chunks(remove, ["delete me"]))

    repository.delete_by_document(remove.id)

    assert len(repository.get_by_document(keep.id)) == 1


def test_replace_swaps_the_old_chunks_for_new_ones(session: Session) -> None:
    document = make_document(session)
    repository = DocumentChunkRepository(session)
    repository.add_many(make_chunks(document, ["old one", "old two", "old three"]))

    repository.replace_for_document(document.id, make_chunks(document, ["new one", "new two"]))

    stored = repository.get_by_document(document.id)
    assert [chunk.text for chunk in stored] == ["new one", "new two"]


def test_replace_reuses_the_same_sequence_numbers(session: Session) -> None:
    """Re-ingesting restarts numbering at 0, so the old chunk 0 must be gone
    before the new one is written."""
    document = make_document(session)
    repository = DocumentChunkRepository(session)
    repository.add_many(make_chunks(document, ["old one", "old two"]))

    repository.replace_for_document(document.id, make_chunks(document, ["new one", "new two"]))

    assert [chunk.sequence for chunk in repository.get_by_document(document.id)] == [0, 1]


# ---------------------------------------------------------------------------
# The database's own guarantees
# ---------------------------------------------------------------------------


def test_the_same_sequence_twice_in_one_document_is_rejected(session: Session) -> None:
    """A document cannot have two chunk 3s — otherwise 'fetch the next chunk'
    would be ambiguous."""
    document = make_document(session)
    repository = DocumentChunkRepository(session)
    repository.add_many(make_chunks(document, ["first"]))

    with pytest.raises(IntegrityError):
        repository.add_many(make_chunks(document, ["duplicate"]))
    session.rollback()
