from datetime import datetime

from sqlmodel import Session, col, select

from foundation.models import IngestionJob, IngestionStatus


class IngestionJobRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def enqueue(self, document_id: int) -> IngestionJob:
        """Add a document to the queue. This is all the upload endpoint does."""
        job = IngestionJob(document_id=document_id)
        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)
        return job

    def claim_next(self) -> IngestionJob | None:
        """Take the oldest pending job and mark it running.

        FOR UPDATE SKIP LOCKED is what makes this safe with more than one worker:
        the row is locked while being claimed, and any other worker skips over it
        instead of waiting. Without it, two workers can pick up the same job and
        ingest the same document twice.
        """
        statement = (
            select(IngestionJob)
            .where(IngestionJob.status == IngestionStatus.PENDING)
            .order_by(col(IngestionJob.id))
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        job = self.session.exec(statement).first()
        if job is None:
            return None

        job.status = IngestionStatus.RUNNING
        job.attempts += 1
        job.updated_at = datetime.now()
        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)
        return job

    def mark_done(self, job: IngestionJob) -> IngestionJob:
        job.status = IngestionStatus.DONE
        job.last_error = None
        job.updated_at = datetime.now()
        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)
        return job

    def mark_for_retry(self, job: IngestionJob, error: str) -> IngestionJob:
        """Put a failed job back in the queue to be tried again later."""
        job.status = IngestionStatus.PENDING
        job.last_error = error
        job.updated_at = datetime.now()
        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)
        return job

    def mark_failed(self, job: IngestionJob, error: str) -> IngestionJob:
        """Give up on a job. It stays in the table so the failure is visible."""
        job.status = IngestionStatus.FAILED
        job.last_error = error
        job.updated_at = datetime.now()
        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)
        return job

    def get_by_document(self, document_id: int) -> list[IngestionJob]:
        statement = (
            select(IngestionJob)
            .where(IngestionJob.document_id == document_id)
            .order_by(col(IngestionJob.id))
        )
        return list(self.session.exec(statement).all())
