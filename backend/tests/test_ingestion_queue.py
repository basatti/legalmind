"""Tests for the background ingestion queue (LEG-59)."""

from foundation.hashing import hash_password
from foundation.models import Case, Document, IngestionStatus, Role, User
from repositories.ingestion_job_repository import IngestionJobRepository


def make_document(session, filename="doc.pdf") -> Document:
    """A document for jobs to point at — the FK requires a real row."""
    user = User(
        email=f"queue-{filename}@example.com",
        full_name="Queue Tester",
        hashed_password=hash_password("password123"),
        role=Role.PARALEGAL,
    )
    case = Case(title="Queue Case", description=None, status="draft")
    session.add(user)
    session.add(case)
    session.commit()
    session.refresh(user)
    session.refresh(case)

    document = Document(
        case_id=case.id,
        filename=filename,
        file_path=f"1/{filename}",
        uploaded_by=user.id,
    )
    session.add(document)
    session.commit()
    session.refresh(document)
    return document


# --- enqueue -----------------------------------------------------------------


def test_enqueue_creates_a_pending_job(session):
    document = make_document(session)
    job = IngestionJobRepository(session).enqueue(document.id)

    assert job.id is not None
    assert job.document_id == document.id
    assert job.status is IngestionStatus.PENDING
    assert job.attempts == 0
    assert job.last_error is None


# --- claiming ----------------------------------------------------------------


def test_claim_returns_none_when_queue_is_empty(session):
    assert IngestionJobRepository(session).claim_next() is None


def test_claim_marks_the_job_running(session):
    document = make_document(session)
    repo = IngestionJobRepository(session)
    repo.enqueue(document.id)

    claimed = repo.claim_next()
    assert claimed is not None
    assert claimed.status is IngestionStatus.RUNNING


def test_claim_takes_the_oldest_job_first(session):
    """FIFO: whatever was queued first must be processed first."""
    document = make_document(session)
    repo = IngestionJobRepository(session)
    first = repo.enqueue(document.id)
    second = repo.enqueue(document.id)

    assert repo.claim_next().id == first.id
    assert repo.claim_next().id == second.id


def test_a_claimed_job_cannot_be_claimed_again(session):
    """Once RUNNING, a job is invisible to other workers — this is what stops
    two workers processing the same document."""
    document = make_document(session)
    repo = IngestionJobRepository(session)
    repo.enqueue(document.id)

    assert repo.claim_next() is not None
    assert repo.claim_next() is None


# --- finishing ---------------------------------------------------------------


def test_mark_done(session):
    document = make_document(session)
    repo = IngestionJobRepository(session)
    repo.enqueue(document.id)
    job = repo.claim_next()

    done = repo.mark_done(job)
    assert done.status is IngestionStatus.DONE
    assert done.last_error is None
    assert repo.claim_next() is None


def test_mark_for_retry_puts_the_job_back_and_records_why(session):
    document = make_document(session)
    repo = IngestionJobRepository(session)
    repo.enqueue(document.id)
    job = repo.claim_next()

    retried = repo.mark_for_retry(job, "parser exploded")
    assert retried.status is IngestionStatus.PENDING
    assert retried.attempts == 1
    assert retried.last_error == "parser exploded"


def test_a_retried_job_is_claimable_again(session):
    document = make_document(session)
    repo = IngestionJobRepository(session)
    enqueued = repo.enqueue(document.id)
    repo.mark_for_retry(repo.claim_next(), "boom")

    again = repo.claim_next()
    assert again is not None
    assert again.id == enqueued.id


def test_attempts_accumulate_across_retries(session):
    document = make_document(session)
    repo = IngestionJobRepository(session)
    repo.enqueue(document.id)

    for expected in (1, 2, 3):
        job = repo.claim_next()
        assert repo.mark_for_retry(job, "again").attempts == expected


def test_mark_failed_stops_the_job_blocking_the_queue(session):
    """A permanently broken document must fail visibly and step aside — its
    error stays readable, but no worker picks it up again."""
    document = make_document(session)
    repo = IngestionJobRepository(session)
    repo.enqueue(document.id)

    failed = repo.mark_failed(repo.claim_next(), "unreadable PDF")
    assert failed.status is IngestionStatus.FAILED
    assert failed.attempts == 1
    assert failed.last_error == "unreadable PDF"
    assert repo.claim_next() is None


def test_a_failed_job_does_not_block_later_jobs(session):
    """The whole point of failing rather than retrying forever."""
    document = make_document(session)
    repo = IngestionJobRepository(session)
    repo.enqueue(document.id)
    second = repo.enqueue(document.id)

    repo.mark_failed(repo.claim_next(), "dead")

    following = repo.claim_next()
    assert following is not None
    assert following.id == second.id
