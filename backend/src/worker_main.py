"""Run-forever entry point for the ingestion worker.

    uv run python -m worker_main

Polls the queue, processes whatever it finds, sleeps only when the queue is
empty. Several of these can run at once — the queue's FOR UPDATE SKIP LOCKED
claim is what makes that safe.

Ctrl-C stops it cleanly: the flag is checked between jobs, so the job in flight
finishes and gets marked rather than being abandoned half-done in RUNNING.
"""

import logging
import signal
import time
from types import FrameType

from foundation.database import get_session
from repositories.ingestion_job_repository import IngestionJobRepository
from services.ingestion_service import ParseAndChunkPipeline
from services.ingestion_worker import IngestionWorker

logger = logging.getLogger(__name__)

IDLE_SLEEP_SECONDS = 5.0

_shutting_down = False


def _request_shutdown(signum: int, frame: FrameType | None) -> None:
    global _shutting_down
    logger.info("shutdown requested — finishing current job then stopping")
    _shutting_down = True


def run_forever() -> None:
    while not _shutting_down:
        # A fresh session per cycle. A long-lived one would eventually hold a
        # stale connection, and a failed job can leave a session unusable.
        session = next(get_session())
        try:
            pipeline = ParseAndChunkPipeline(session)
            worker = IngestionWorker(IngestionJobRepository(session), pipeline)
            did_work = worker.run_once()
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
