"""Tests for the parse-chunk-embed-store pipeline (LEG-13 / LEG-59)."""

import pytest

from embeddings.offline import OfflineEmbeddingProvider
from foundation.hashing import hash_password
from foundation.models import EMBEDDING_DIMENSIONS, Case, Document, Role, User
from parsers.base import ParserError
from repositories.document_chunk_repository import DocumentChunkRepository
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


def build_pipeline(session, **kwargs) -> ParseAndChunkPipeline:
    kwargs.setdefault(
        "embedding_provider", OfflineEmbeddingProvider(dimensions=EMBEDDING_DIMENSIONS)
    )
    return ParseAndChunkPipeline(session, **kwargs)


def test_ingest_raises_for_a_document_that_does_not_exist(session):
    pipeline = build_pipeline(session)
    with pytest.raises(ValueError, match="no longer exists"):
        pipeline.ingest(document_id=999999)


def test_a_provider_with_the_wrong_width_is_rejected_at_construction(session):
    with pytest.raises(ValueError, match="wide vectors"):
        build_pipeline(session, embedding_provider=OfflineEmbeddingProvider(dimensions=8))


def test_ingest_returns_the_chunk_count(session, minimal_pdf_bytes):
    document = make_document(session, minimal_pdf_bytes)
    pipeline = build_pipeline(session)

    count = pipeline.ingest(document.id)
    assert count > 0


def test_ingest_reads_the_right_document(session, minimal_pdf_bytes):
    """Enqueue two documents; ingesting one must not touch the other's file."""
    from unittest.mock import MagicMock

    first = make_document(session, minimal_pdf_bytes, filename="a.pdf")
    second = make_document(session, minimal_pdf_bytes, filename="b.pdf")

    files = MagicMock()
    files.read.return_value = minimal_pdf_bytes
    pipeline = build_pipeline(session, files=files)

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

    pipeline = build_pipeline(session)
    with pytest.raises(FileNotFoundError):
        pipeline.ingest(document.id)


# ---------------------------------------------------------------------------
# Persistence (LEG-58)
# ---------------------------------------------------------------------------


def test_ingest_persists_a_chunk_row_per_chunk(session, minimal_pdf_bytes):
    document = make_document(session, minimal_pdf_bytes)
    pipeline = build_pipeline(session)

    count = pipeline.ingest(document.id)

    stored = DocumentChunkRepository(session).get_by_document(document.id)
    assert len(stored) == count
    assert all(chunk.case_id == document.case_id for chunk in stored)
    assert all(len(chunk.embedding) == EMBEDDING_DIMENSIONS for chunk in stored)


def test_ingest_replaces_rather_than_duplicates_chunks_on_forced_rerun(
    session, minimal_pdf_bytes
):
    document = make_document(session, minimal_pdf_bytes)
    pipeline = build_pipeline(session)

    first = pipeline.ingest(document.id)
    second = pipeline.ingest(document.id, force=True)

    stored = DocumentChunkRepository(session).get_by_document(document.id)
    assert len(stored) == second == first


# ---------------------------------------------------------------------------
# Skipping unchanged content (LEG-60)
# ---------------------------------------------------------------------------


def test_a_first_run_ingests_and_records_the_fingerprint(session, minimal_pdf_bytes):
    document = make_document(session, minimal_pdf_bytes)
    pipeline = build_pipeline(session)

    stored = pipeline.ingest(document.id)

    assert stored > 0
    session.refresh(document)
    assert document.ingested_content_hash is not None


def test_a_second_run_on_unchanged_content_does_nothing(session, minimal_pdf_bytes):
    document = make_document(session, minimal_pdf_bytes)
    pipeline = build_pipeline(session)
    first = pipeline.ingest(document.id)

    second = pipeline.ingest(document.id)

    assert second == 0
    assert len(DocumentChunkRepository(session).get_by_document(document.id)) == first


def test_force_ingests_again_even_when_nothing_changed(session, minimal_pdf_bytes):
    """Needed after changing chunk size or embedding model, when the bytes are
    the same but the chunks should be rebuilt."""
    document = make_document(session, minimal_pdf_bytes)
    pipeline = build_pipeline(session)
    pipeline.ingest(document.id)

    assert pipeline.ingest(document.id, force=True) > 0


def test_a_failed_run_does_not_record_a_fingerprint(session):
    """Otherwise a document that failed would be skipped forever, holding no
    chunks and looking finished."""
    document = make_document(session, b"this is not a pdf at all")
    pipeline = build_pipeline(session)

    with pytest.raises(ParserError):
        pipeline.ingest(document.id)

    session.refresh(document)
    assert document.ingested_content_hash is None
