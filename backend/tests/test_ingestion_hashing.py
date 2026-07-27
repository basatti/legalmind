"""Tests for skipping unchanged documents (LEG-13, stage 6)."""

from uuid import uuid4

import pytest
from sqlmodel import Session

from embeddings import OfflineEmbeddingProvider
from foundation.hashing import hash_content, hash_password
from foundation.models import EMBEDDING_DIMENSIONS, Case, Document, Role, User
from foundation.storage import StorageBackend
from repositories.document_chunk_repository import DocumentChunkRepository
from repositories.document_repository import DocumentRepository
from services.ingestion_service import IngestionError, IngestionService
from tests.test_parsers import build_pdf
from parsers import ParserError


class InMemoryStorage(StorageBackend):
    """Storage that keeps files in a dict, so tests never touch the disk."""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    def save(self, case_id: int, filename: str, content: bytes) -> str:
        path = f"{case_id}/{filename}"
        self.files[path] = content
        return path

    def read(self, file_path: str) -> bytes:
        return self.files[file_path]

    def delete(self, file_path: str) -> None:
        self.files.pop(file_path, None)


def make_document(session: Session, store: InMemoryStorage, content: bytes) -> Document:
    user = User(
        email=f"hash-{uuid4()}@example.com",
        full_name="Hash Test",
        hashed_password="not-a-real-hash",
        role=Role.ATTORNEY,
    )
    case = Case(title="Hash test case")
    session.add(user)
    session.add(case)
    session.commit()
    session.refresh(user)
    session.refresh(case)

    assert case.id is not None
    path = store.save(case_id=case.id, filename="contract.pdf", content=content)

    document = Document(
        case_id=case.id,
        filename="contract.pdf",
        file_path=path,
        uploaded_by=user.id,
    )
    session.add(document)
    session.commit()
    session.refresh(document)
    return document


def build_service(session: Session, store: InMemoryStorage) -> IngestionService:
    return IngestionService(
        document_repository=DocumentRepository(session),
        chunk_repository=DocumentChunkRepository(session),
        embedding_provider=OfflineEmbeddingProvider(dimensions=EMBEDDING_DIMENSIONS),
        storage_backend=store,
    )


# ---------------------------------------------------------------------------
# The fingerprint itself
# ---------------------------------------------------------------------------


def test_identical_bytes_give_an_identical_fingerprint() -> None:
    assert hash_content(b"a lease clause") == hash_content(b"a lease clause")


def test_different_bytes_give_a_different_fingerprint() -> None:
    assert hash_content(b"a lease clause") != hash_content(b"a lease clauses")


def test_content_hashing_is_not_password_hashing() -> None:
    """The two functions in hashing.py have opposite requirements: passwords must
    hash differently every time, content must hash the same every time."""
    assert hash_password("secret") != hash_password("secret")
    assert hash_content(b"secret") == hash_content(b"secret")


# ---------------------------------------------------------------------------
# Skipping work
# ---------------------------------------------------------------------------


def test_a_first_run_ingests_and_records_the_fingerprint(session: Session) -> None:
    store = InMemoryStorage()
    document = make_document(session, store, build_pdf(["Clause one", "Clause two"]))

    stored = build_service(session, store).ingest_document(document.id)

    assert stored > 0
    session.refresh(document)
    assert document.ingested_content_hash is not None


def test_a_second_run_on_unchanged_content_does_nothing(session: Session) -> None:
    store = InMemoryStorage()
    document = make_document(session, store, build_pdf(["Clause one", "Clause two"]))
    service = build_service(session, store)
    first = service.ingest_document(document.id)

    second = service.ingest_document(document.id)

    assert second == 0
    assert len(DocumentChunkRepository(session).get_by_document(document.id)) == first


def test_force_ingests_again_even_when_nothing_changed(session: Session) -> None:
    """Needed after changing chunk size or embedding model, when the bytes are
    the same but the chunks should be rebuilt."""
    store = InMemoryStorage()
    document = make_document(session, store, build_pdf(["Clause one", "Clause two"]))
    service = build_service(session, store)
    service.ingest_document(document.id)

    assert service.ingest_document(document.id, force=True) > 0


def test_changed_content_is_ingested_again(session: Session) -> None:
    store = InMemoryStorage()
    document = make_document(session, store, build_pdf(["Clause one"]))
    service = build_service(session, store)
    service.ingest_document(document.id)

    store.files[document.file_path] = build_pdf(["Completely different text now"])

    assert service.ingest_document(document.id) > 0


def test_a_failed_run_does_not_record_a_fingerprint(session: Session) -> None:
    """Otherwise a document that failed would be skipped forever, holding no
    chunks and looking finished."""
    store = InMemoryStorage()
    document = make_document(session, store, b"this is not a pdf at all")
    service = build_service(session, store)

    with pytest.raises(ParserError):
        service.ingest_document(document.id)

    session.refresh(document)
    assert document.ingested_content_hash is None
