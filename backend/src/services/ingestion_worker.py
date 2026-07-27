"""Drains the ingestion queue (LEG-13, stage 5).

Claims one job at a time, runs the pipeline on it, and records the outcome.
Deliberately knows nothing about HTTP — it is only a loop over the queue.
"""

from sqlmodel import Session

from foundation.models import IngestionJob
from repositories.ingestion_job_repository import IngestionJobRepository
from services.ingestion_service import IngestionService


class IngestionWorker:
    def __init__(
        self,
        session: Session,
        job_repository: IngestionJobRepository,
        ingestion_service: IngestionService,
        max_attempts: int = 3,
    ) -> None:
        self.session = session
        self.job_repository = job_repository
        self.ingestion_service = ingestion_service
        self.max_attempts = max_attempts

    def run_once(self) -> bool:
        """Claim and process a single job.

        Returns True if there was a job to do, False if the queue was empty.
        """
        job = self.job_repository.claim_next()
        if job is None:
            return False

        try:
            self.ingestion_service.ingest_document(job.document_id)
        except Exception as exc:
            # Only roll back if the failure actually broke the transaction, which
            # is_active reports. A parser or network error leaves the session
            # perfectly usable, and rolling back anyway would discard the claim
            # that was just committed.
            if not self.session.is_active:
                self.session.rollback()
            self._record_failure(job, exc)
        else:
            self.job_repository.mark_done(job)

        return True

    def drain(self, limit: int | None = None) -> int:
        """Process jobs until the queue is empty. Returns how many were handled."""
        processed = 0
        while limit is None or processed < limit:
            if not self.run_once():
                break
            processed += 1
        return processed

    def _record_failure(self, job: IngestionJob, exc: Exception) -> None:
        """Retry a few times, then give up and leave the reason behind."""
        reason = f"{type(exc).__name__}: {exc}"
        if job.attempts >= self.max_attempts:
            self.job_repository.mark_failed(job, reason)
        else:
            self.job_repository.mark_for_retry(job, reason)
