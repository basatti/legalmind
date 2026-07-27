"""Tests for the ingestion queue and worker (LEG-13, stage 5)."""

from uuid import uuid4

from sqlmodel import Session

from foundation.models import Case, Document, IngestionStatus, Role, User
from repositories.ingestion_job_repository import IngestionJobRepository
from services.ingestion_worker import IngestionWorker


def make_document(session: Session) -> Document:
    """A real case + document, since a job points at one by foreign key."""
    user = User(
        email=f"queue-{uuid4()}@example.com",
        full_name="Queue Test",
        hashed_password="not-a-real-hash",
        role=Role.ATTORNEY,
    )
    case = Case(title="Queue test case")
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


class StubIngestionService:
    """Stands in for the real pipeline.

    Lets a failure be produced on demand — a corrupt PDF is hard to arrange,
    but an exception is not.
    """

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[int] = []

    def ingest_document(self, document_id: int) -> int:
        self.calls.append(document_id)
        if self.error is not None:
            raise self.error
        return 3


# ---------------------------------------------------------------------------
# The queue
# ---------------------------------------------------------------------------


def test_enqueue_creates_a_pending_job(session: Session) -> None:
    document = make_document(session)
    job = IngestionJobRepository(session).enqueue(document.id)

    assert job.status == IngestionStatus.PENDING
    assert job.attempts == 0
    assert job.document_id == document.id


def test_claim_next_returns_nothing_when_the_queue_is_empty(session: Session) -> None:
    assert IngestionJobRepository(session).claim_next() is None


def test_claim_next_marks_the_job_running_and_counts_the_attempt(session: Session) -> None:
    document = make_document(session)
    repository = IngestionJobRepository(session)
    repository.enqueue(document.id)

    job = repository.claim_next()

    assert job is not None
    assert job.status == IngestionStatus.RUNNING
    assert job.attempts == 1


def test_claim_next_takes_the_oldest_job_first(session: Session) -> None:
    """A queue is first-in first-out — otherwise a busy day could starve the
    document someone uploaded this morning."""
    first = make_document(session)
    second = make_document(session)
    repository = IngestionJobRepository(session)
    repository.enqueue(first.id)
    repository.enqueue(second.id)

    claimed = repository.claim_next()

    assert claimed is not None
    assert claimed.document_id == first.id


def test_claim_next_does_not_hand_out_the_same_job_twice(session: Session) -> None:
    document = make_document(session)
    repository = IngestionJobRepository(session)
    repository.enqueue(document.id)

    repository.claim_next()

    assert repository.claim_next() is None


# ---------------------------------------------------------------------------
# The worker
# ---------------------------------------------------------------------------


def test_worker_reports_no_work_when_the_queue_is_empty(session: Session) -> None:
    worker = IngestionWorker(session, IngestionJobRepository(session), StubIngestionService())

    assert worker.run_once() is False


def test_worker_runs_the_pipeline_and_marks_the_job_done(session: Session) -> None:
    document = make_document(session)
    repository = IngestionJobRepository(session)
    repository.enqueue(document.id)
    service = StubIngestionService()

    did_work = IngestionWorker(session, repository, service).run_once()

    assert did_work is True
    assert service.calls == [document.id]
    assert repository.get_by_document(document.id)[0].status == IngestionStatus.DONE


def test_a_failure_goes_back_in_the_queue_to_be_retried(session: Session) -> None:
    document = make_document(session)
    repository = IngestionJobRepository(session)
    repository.enqueue(document.id)
    service = StubIngestionService(error=RuntimeError("network went away"))

    IngestionWorker(session, repository, service, max_attempts=3).run_once()

    job = repository.get_by_document(document.id)[0]
    assert job.status == IngestionStatus.PENDING
    assert job.attempts == 1
    assert "network went away" in (job.last_error or "")


def test_the_worker_gives_up_after_the_attempt_limit(session: Session) -> None:
    """A genuinely broken file fails identically every time — retrying forever
    would block every good document behind it."""
    document = make_document(session)
    repository = IngestionJobRepository(session)
    repository.enqueue(document.id)
    service = StubIngestionService(error=ValueError("PDF is password-protected"))

    IngestionWorker(session, repository, service, max_attempts=1).run_once()

    job = repository.get_by_document(document.id)[0]
    assert job.status == IngestionStatus.FAILED
    assert "password-protected" in (job.last_error or "")


def test_one_bad_document_does_not_stop_the_worker(session: Session) -> None:
    """The worker must survive a failure, not die on it."""
    document = make_document(session)
    repository = IngestionJobRepository(session)
    repository.enqueue(document.id)
    worker = IngestionWorker(
        session, repository, StubIngestionService(error=RuntimeError("boom")), max_attempts=1
    )

    worker.run_once()  # must not raise

    assert repository.get_by_document(document.id)[0].status == IngestionStatus.FAILED


def test_drain_works_through_every_queued_job(session: Session) -> None:
    documents = [make_document(session) for _ in range(3)]
    repository = IngestionJobRepository(session)
    for document in documents:
        repository.enqueue(document.id)
    service = StubIngestionService()

    processed = IngestionWorker(session, repository, service).drain()

    assert processed == 3
    assert service.calls == [document.id for document in documents]
