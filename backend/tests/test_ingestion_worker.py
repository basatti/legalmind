"""Tests for the ingestion worker (LEG-59).

The worker is tested against fake pipelines rather than real PDFs: what is
under test here is the queue mechanics — claiming, retrying, giving up — and a
real parser would only make these tests slower and less precise.
"""

from datetime import datetime, timedelta

from foundation.hashing import hash_password
from foundation.models import Case, Document, IngestionStatus, Role, User
from repositories.ingestion_job_repository import IngestionJobRepository
from services.ingestion_worker import IngestionWorker


class SucceedingPipeline:
    """Records what it was asked to process, and claims 5 chunks each time."""

    def __init__(self) -> None:
        self.seen: list[int] = []

    def ingest(self, document_id: int) -> int:
        self.seen.append(document_id)
        return 5


class FailingPipeline:
    """Always raises, so retry and give-up behaviour can be exercised."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error or ValueError("pipeline exploded")
        self.calls = 0

    def ingest(self, document_id: int) -> int:
        self.calls += 1
        raise self.error


def make_document(session, filename="doc.pdf") -> Document:
    user = User(
        email=f"worker-{filename}@example.com",
        full_name="Worker Tester",
        hashed_password=hash_password("password123"),
        role=Role.PARALEGAL,
    )
    case = Case(title="Worker Case", description=None, status="draft")
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


# --- empty queue -------------------------------------------------------------


def test_run_once_returns_false_on_an_empty_queue(session):
    worker = IngestionWorker(IngestionJobRepository(session), SucceedingPipeline())
    assert worker.run_once() is False


def test_drain_on_an_empty_queue_does_nothing(session):
    worker = IngestionWorker(IngestionJobRepository(session), SucceedingPipeline())
    assert worker.drain() == 0


# --- the happy path ----------------------------------------------------------


def test_a_successful_job_is_marked_done(session):
    document = make_document(session)
    jobs = IngestionJobRepository(session)
    job = jobs.enqueue(document.id)
    pipeline = SucceedingPipeline()

    assert IngestionWorker(jobs, pipeline).run_once() is True
    session.refresh(job)
    assert job.status is IngestionStatus.DONE
    assert job.last_error is None


def test_the_pipeline_is_given_the_right_document(session):
    document = make_document(session)
    jobs = IngestionJobRepository(session)
    jobs.enqueue(document.id)
    pipeline = SucceedingPipeline()

    IngestionWorker(jobs, pipeline).run_once()
    assert pipeline.seen == [document.id]


def test_drain_processes_every_queued_job(session):
    document = make_document(session)
    jobs = IngestionJobRepository(session)
    for _ in range(3):
        jobs.enqueue(document.id)
    pipeline = SucceedingPipeline()

    assert IngestionWorker(jobs, pipeline).drain() == 3
    assert len(pipeline.seen) == 3


# --- failure and retry -------------------------------------------------------


def test_a_failed_job_is_requeued_with_the_reason(session):
    document = make_document(session)
    jobs = IngestionJobRepository(session)
    job = jobs.enqueue(document.id)

    IngestionWorker(jobs, FailingPipeline()).run_once()
    session.refresh(job)
    assert job.status is IngestionStatus.PENDING
    assert job.attempts == 1
    assert job.last_error is not None


def test_the_error_records_the_exception_type(session):
    """last_error should name the failing stage, not just the message."""
    document = make_document(session)
    jobs = IngestionJobRepository(session)
    job = jobs.enqueue(document.id)

    IngestionWorker(jobs, FailingPipeline(RuntimeError("bad pdf"))).run_once()
    session.refresh(job)
    assert job.last_error == "RuntimeError: bad pdf"


def test_a_job_fails_for_good_once_attempts_are_spent(session):
    document = make_document(session)
    jobs = IngestionJobRepository(session)
    job = jobs.enqueue(document.id)
    worker = IngestionWorker(jobs, FailingPipeline(), max_attempts=3)

    worker.run_once()
    session.refresh(job)
    assert (job.status, job.attempts) == (IngestionStatus.PENDING, 1)

    worker.run_once()
    session.refresh(job)
    assert (job.status, job.attempts) == (IngestionStatus.PENDING, 2)

    worker.run_once()
    session.refresh(job)
    assert (job.status, job.attempts) == (IngestionStatus.FAILED, 3)


def test_max_attempts_is_honoured(session):
    """max_attempts=1 means no retry at all — fail on the first try."""
    document = make_document(session)
    jobs = IngestionJobRepository(session)
    job = jobs.enqueue(document.id)

    IngestionWorker(jobs, FailingPipeline(), max_attempts=1).run_once()
    session.refresh(job)
    assert job.status is IngestionStatus.FAILED


def test_run_once_returns_true_even_when_the_job_failed(session):
    """A failure is still work done — the loop must keep going, not stop dead."""
    document = make_document(session)
    jobs = IngestionJobRepository(session)
    jobs.enqueue(document.id)

    assert IngestionWorker(jobs, FailingPipeline()).run_once() is True


def test_a_broken_document_does_not_block_the_queue(session):
    """The core requirement: one unprocessable document must not stop the
    documents queued behind it."""
    broken = make_document(session, filename="broken.pdf")
    healthy = make_document(session, filename="healthy.pdf")
    jobs = IngestionJobRepository(session)
    broken_job = jobs.enqueue(broken.id)
    healthy_job = jobs.enqueue(healthy.id)

    class FailsOnlyTheBrokenOne:
        def __init__(self) -> None:
            self.succeeded: list[int] = []

        def ingest(self, document_id: int) -> int:
            if document_id == broken.id:
                raise ValueError("cannot read this one")
            self.succeeded.append(document_id)
            return 2

    pipeline = FailsOnlyTheBrokenOne()
    IngestionWorker(jobs, pipeline, max_attempts=1).drain()

    session.refresh(broken_job)
    session.refresh(healthy_job)
    assert broken_job.status is IngestionStatus.FAILED
    assert healthy_job.status is IngestionStatus.DONE
    assert pipeline.succeeded == [healthy.id]


def test_drain_terminates_when_a_job_keeps_failing(session):
    """drain() must not spin forever on a job that always fails — attempts are
    what guarantee it eventually stops."""
    document = make_document(session)
    jobs = IngestionJobRepository(session)
    jobs.enqueue(document.id)

    handled = IngestionWorker(jobs, FailingPipeline(), max_attempts=3).drain()
    assert handled == 3


# --- workers that die mid-job ------------------------------------------------


def abandon(session, jobs, job) -> None:
    """Simulate a worker dying mid-job: the claim is made, then nothing.

    Backdating updated_at stands in for the passage of time, so the test does
    not have to wait for a real timeout.
    """
    jobs.claim_next()
    job.updated_at = datetime.now() - timedelta(hours=2)
    session.add(job)
    session.commit()


def test_reclaim_stale_puts_an_abandoned_job_back_on_the_queue(session):
    document = make_document(session)
    jobs = IngestionJobRepository(session)
    job = jobs.enqueue(document.id)
    abandon(session, jobs, job)

    worker = IngestionWorker(jobs, SucceedingPipeline())
    assert worker.reclaim_stale(timedelta(minutes=30)) == 1

    session.refresh(job)
    assert job.status is IngestionStatus.PENDING
    assert job.attempts == 1
    assert job.last_error is not None
    assert job.last_error.startswith("StaleJobError:")


def test_a_reclaimed_job_is_actually_processed(session):
    """The point of reclaiming: the document ends up ingested, not just requeued."""
    document = make_document(session)
    jobs = IngestionJobRepository(session)
    job = jobs.enqueue(document.id)
    abandon(session, jobs, job)

    pipeline = SucceedingPipeline()
    worker = IngestionWorker(jobs, pipeline)
    worker.reclaim_stale(timedelta(minutes=30))

    assert worker.run_once() is True
    assert pipeline.seen == [document.id]
    session.refresh(job)
    assert job.status is IngestionStatus.DONE


def test_reclaim_stale_leaves_a_job_that_is_still_running(session):
    """Reclaiming a live job would put two workers on one document — the one
    failure this timeout exists to avoid."""
    document = make_document(session)
    jobs = IngestionJobRepository(session)
    jobs.enqueue(document.id)
    jobs.claim_next()

    worker = IngestionWorker(jobs, SucceedingPipeline())
    assert worker.reclaim_stale(timedelta(minutes=30)) == 0


def test_a_job_that_keeps_killing_the_worker_eventually_fails(session):
    """Reclaim goes through the same attempts limit as an ordinary failure, so
    a document that crashes the worker cannot resurrect forever."""
    document = make_document(session)
    jobs = IngestionJobRepository(session)
    job = jobs.enqueue(document.id)
    worker = IngestionWorker(jobs, SucceedingPipeline(), max_attempts=2)

    abandon(session, jobs, job)
    worker.reclaim_stale(timedelta(minutes=30))
    session.refresh(job)
    assert (job.status, job.attempts) == (IngestionStatus.PENDING, 1)

    abandon(session, jobs, job)
    worker.reclaim_stale(timedelta(minutes=30))
    session.refresh(job)
    assert (job.status, job.attempts) == (IngestionStatus.FAILED, 2)
