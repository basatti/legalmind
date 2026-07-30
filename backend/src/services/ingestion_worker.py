"""Drains the ingestion queue.

Producer–consumer (CS concept): uploads produce jobs, this consumes them. The
two never wait on each other — an upload returns as soon as the row is written,
and this runs independently, possibly on another machine.

This class owns the queue mechanics only: claim a job, run it, record the
outcome, decide whether a failure is worth retrying. It knows nothing about
PDFs, chunks or embeddings — that is the pipeline's business, reached through
the Pipeline protocol below. Keeping the split means the retry logic can be
tested without a real document, and the pipeline can be tested without a queue.
"""

import logging
from typing import Protocol

from foundation.models import IngestionJob
from repositories.ingestion_job_repository import IngestionJobRepository

logger = logging.getLogger(__name__)

DEFAULT_MAX_ATTEMPTS = 3


class Pipeline(Protocol):
    """Whatever actually processes a document.

    A Protocol rather than an ABC so the worker imposes nothing on its
    collaborator — anything with this one method fits, including the eventual
    parse → chunk → embed → store service and a fake in tests.
    """

    def ingest(self, document_id: int) -> int:
        """Process one document. Returns how many chunks were stored.

        Must raise on failure rather than returning 0 — the worker decides what
        a failure means, and it can only do that if it hears about one.
        """
        ...


class IngestionWorker:
    def __init__(
        self,
        jobs: IngestionJobRepository,
        pipeline: Pipeline,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> None:
        self.jobs = jobs
        self.pipeline = pipeline
        self.max_attempts = max_attempts

    def run_once(self) -> bool:
        """Process at most one job. Returns False when the queue is empty.

        The return value is what lets a caller tell "nothing to do, go to sleep"
        apart from "did some work, come straight back for more".
        """
        job = self.jobs.claim_next()
        if job is None:
            return False

        try:
            stored = self.pipeline.ingest(job.document_id)
        except Exception as exc:
            self._handle_failure(job, exc)
            return True

        self.jobs.mark_done(job)
        logger.info("ingested document %s into %s chunks", job.document_id, stored)
        return True

    def drain(self) -> int:
        """Process jobs until the queue is empty. Returns how many were handled.

        Note this counts jobs *attempted*, not jobs that succeeded — a job that
        failed and was requeued will be picked up again, which is intentional.
        """
        handled = 0
        while self.run_once():
            handled += 1
        return handled

    def _handle_failure(self, job: IngestionJob, exc: Exception) -> None:
        """Requeue a failed job, or give up on it once its attempts are spent.

        The error text records the exception type as well as its message, so the
        database says which stage broke — "ParserError: ..." is far more use than
        a bare message when reading last_error weeks later.
        """
        reason = f"{type(exc).__name__}: {exc}"

        if job.attempts + 1 >= self.max_attempts:
            self.jobs.mark_failed(job, reason)
            logger.error(
                "giving up on document %s after %s attempts: %s",
                job.document_id,
                job.attempts + 1,
                reason,
            )
            return

        self.jobs.mark_for_retry(job, reason)
        logger.warning("retrying document %s: %s", job.document_id, reason)
