"""Tests for the parse-and-chunk pipeline (LEG-59)."""

import pytest

from foundation.hashing import hash_password
from foundation.models import Case, Document, Role, User
from services.ingestion_service import ParseAndChunkPipeline


def make_document(session, content: bytes, filename="doc.pdf") -> Document:
    """A document whose bytes are actually on disk, via the real storage
    backend — the pipeline reads through StorageBackend, not a fake."""
    from foundation.storage import storage

    user = User(
        email=f"pipeline-{filename}@example.com",
        full_name="Pipeline Tester",
        hashed_password=hash_password("password123"),
        role=Role.PARALEGAL,
    )
    case = Case(title="Pipeline Case", description=None, status="draft")
    session.add(user)
    session.add(case)
    session.commit()
    session.refresh(user)
    session.refresh(case)

    file_path = storage.save(case_id=case.id, filename=filename, content=content)
    document = Document(
        case_id=case.id,
        filename=filename,
        file_path=file_path,
        uploaded_by=user.id,
    )
    session.add(document)
    session.commit()
    session.refresh(document)
    return document


def test_ingest_raises_for_a_document_that_does_not_exist(session):
    pipeline = ParseAndChunkPipeline(session)
    with pytest.raises(ValueError, match="no longer exists"):
        pipeline.ingest(document_id=999999)


def test_ingest_returns_the_chunk_count(session, minimal_pdf_bytes):
    document = make_document(session, minimal_pdf_bytes)
    pipeline = ParseAndChunkPipeline(session)

    count = pipeline.ingest(document.id)
    assert count > 0


def test_ingest_reads_the_right_document(session, minimal_pdf_bytes):
    """Enqueue two documents; ingesting one must not touch the other's file."""
    from unittest.mock import MagicMock

    first = make_document(session, minimal_pdf_bytes, filename="a.pdf")
    second = make_document(session, minimal_pdf_bytes, filename="b.pdf")

    files = MagicMock()
    files.read.return_value = minimal_pdf_bytes
    pipeline = ParseAndChunkPipeline(session, files=files)

    pipeline.ingest(first.id)
    files.read.assert_called_once_with(first.file_path)
    assert files.read.call_args[0][0] != second.file_path


def test_a_missing_file_on_disk_surfaces_as_a_real_error(session, minimal_pdf_bytes):
    """The worker needs a real exception to decide whether to retry — a file
    that vanished from disk must not look like an empty successful ingest."""
    document = make_document(session, minimal_pdf_bytes)
    document.file_path = "nowhere/does-not-exist.pdf"
    session.add(document)
    session.commit()

    pipeline = ParseAndChunkPipeline(session)
    with pytest.raises(FileNotFoundError):
        pipeline.ingest(document.id)
