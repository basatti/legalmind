"""Queue operations for background ingestion jobs.

All the SQL for the ingestionjob table lives here, matching how every other
table in this project is accessed — services call these methods and never
write queries themselves.
"""

from datetime import datetime

from sqlmodel import Session, col, select

from foundation.models import IngestionJob, IngestionStatus


class IngestionJobRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def enqueue(self, document_id: int) -> IngestionJob:
        """Add a document to the back of the queue."""
        job = IngestionJob(document_id=document_id)
        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)
        return job

    def claim_next(self) -> IngestionJob | None:
        """Take the oldest pending job and mark it RUNNING, or return None.

        FOR UPDATE SKIP LOCKED is what makes this safe with several workers
        running at once: the row is locked while this transaction holds it, and
        any other worker asking the same question skips past it rather than
        waiting. Without SKIP LOCKED two workers would either block on each
        other or both process the same document.

        The claim is committed before the caller does any work, so the job is
        visibly RUNNING for the whole time it is being processed.
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
        """Put a failed job back on the queue, remembering why it failed."""
        job.status = IngestionStatus.PENDING
        job.attempts += 1
        job.last_error = error
        job.updated_at = datetime.now()
        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)
        return job

    def mark_failed(self, job: IngestionJob, error: str) -> IngestionJob:
        """Give up on a job. It stops blocking the queue but stays inspectable."""
        job.status = IngestionStatus.FAILED
        job.attempts += 1
        job.last_error = error
        job.updated_at = datetime.now()
        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)
        return job
