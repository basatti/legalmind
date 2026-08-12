"""Run-forever entry point for the ingestion worker.

    uv run python -m worker_main

Polls the queue, processes whatever it finds, sleeps only when the queue is
empty. Several of these can run at once — the queue's FOR UPDATE SKIP LOCKED
claim is what makes that safe.

Ctrl-C stops it cleanly: the flag is checked between jobs, so the job in flight
finishes and gets marked rather than being abandoned half-done in RUNNING.

It also sweeps expired sessions away on an interval. That is admittedly not
ingestion, and putting it here makes this "the process that runs background
work" rather than "the process that ingests documents". The alternative was a
second deployable unit — a cron entry or another compose service — for one
DELETE that runs once an hour. This loop already exists, already opens a
database session per cycle, and already shuts down cleanly; a whole process to
avoid a twelve-line function is the worse trade. If a third unrelated chore
ever appears, that is the signal to split them out rather than keep adding.
"""

import logging
import signal
import time
from datetime import UTC, datetime, timedelta
from types import FrameType

from sqlmodel import Session

from embeddings.company_api import CompanyEmbeddingProvider
from foundation import settings
from foundation.database import get_session
from repositories.ingestion_job_repository import IngestionJobRepository
from repositories.session_repository import SessionRepository
from services.ingestion_service import ParseAndChunkPipeline
from services.ingestion_worker import IngestionWorker

logger = logging.getLogger(__name__)

IDLE_SLEEP_SECONDS = 5.0

SESSION_REAP_INTERVAL = timedelta(minutes=settings.SESSION_REAP_INTERVAL_MINUTES)

_shutting_down = False


def _request_shutdown(signum: int, frame: FrameType | None) -> None:
    global _shutting_down
    logger.info("shutdown requested — finishing current job then stopping")
    _shutting_down = True


def reap_due(now: datetime, last_reap: datetime | None, interval: timedelta) -> bool:
    """Whether the expired-session sweep should run on this cycle.

    Split out from the loop because the loop never returns and so cannot be
    tested; this is the whole scheduling decision and it is a pure function of
    three values. `None` means the process has not swept yet, which counts as
    due — a worker restarted every few minutes would otherwise never reach the
    interval and never sweep at all.
    """
    return last_reap is None or now - last_reap >= interval


def reap_expired_sessions(session: Session, now: datetime) -> None:
    """Sweep expired sessions, logging rather than raising on failure.

    Failures are swallowed on purpose. This worker's actual job is draining the
    ingestion queue, and a document that never becomes searchable is a user-
    visible failure in a way that a session row surviving an extra hour is not.
    A broken sweep must not take the queue down with it.
    """
    try:
        deleted = SessionRepository(session).delete_expired(now)
    except Exception:
        logger.exception("expired-session sweep failed; retrying at the next interval")
        return

    if deleted:
        logger.info("deleted %s expired session(s)", deleted)


def run_one_cycle(
    session: Session,
    worker: IngestionWorker,
    now: datetime,
    last_reap: datetime | None,
) -> tuple[bool, datetime | None]:
    """One pass of the loop: reclaim, maybe reap, then claim and process a job.

    Split out of `run_forever` because that loop never returns, so nothing it
    does could be tested — `--cov=worker_main` put the whole body at 53% and
    made that visible. Everything the loop decides now lives here, where a test
    can drive a single cycle with a fake worker; `run_forever` keeps only the
    parts that genuinely cannot be tested, namely the `while`, the sleep and
    the session lifetime.

    `now` and `last_reap` are passed in and handed back rather than kept as
    state here, for the same reason `delete_expired` takes `now`: a cycle that
    reads its own clock cannot be tested without patching time.
    """
    # Before claiming, put back anything a dead worker left RUNNING — nothing
    # else ever will, since only PENDING jobs are claimed. Safe to run from
    # every worker at once: the sweep skips locked rows.
    reclaimed = worker.reclaim_stale()
    if reclaimed:
        logger.warning("reclaimed %s job(s) abandoned by a dead worker", reclaimed)

    if reap_due(now, last_reap, SESSION_REAP_INTERVAL):
        # Stamped before the attempt, not after. A sweep that keeps failing
        # would otherwise be due on every cycle and log the same traceback
        # every five seconds.
        last_reap = now
        reap_expired_sessions(session, now)

    return worker.run_once(), last_reap


def run_forever() -> None:
    # Constructed once per process, not once per job. Must be the same model
    # query_router.py uses for questions — vectors from two different models
    # cannot be compared at all.
    embedding_provider = CompanyEmbeddingProvider()

    # Local rather than module-level: the schedule belongs to this loop, and a
    # global would make two workers in one process share a clock they should
    # not.
    last_reap: datetime | None = None

    while not _shutting_down:
        # A fresh session per cycle. A long-lived one would eventually hold a
        # stale connection, and a failed job can leave a session unusable.
        session = next(get_session())
        try:
            pipeline = ParseAndChunkPipeline(session, embedding_provider=embedding_provider)
            worker = IngestionWorker(IngestionJobRepository(session), pipeline)

            did_work, last_reap = run_one_cycle(session, worker, datetime.now(UTC), last_reap)
        finally:
            session.close()

        if not did_work:
            time.sleep(IDLE_SLEEP_SECONDS)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    )
    signal.signal(signal.SIGINT, _request_shutdown)
    signal.signal(signal.SIGTERM, _request_shutdown)

    logger.info("ingestion worker started")
    run_forever()
    logger.info("ingestion worker stopped")


if __name__ == "__main__":
    main()
