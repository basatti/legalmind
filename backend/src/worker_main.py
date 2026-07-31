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

from embeddings.offline import OfflineEmbeddingProvider
from foundation.database import get_session
from foundation.models import EMBEDDING_DIMENSIONS
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
    # OfflineEmbeddingProvider is hash-based and captures no meaning — see its
    # docstring. It's used here because no real model has been chosen yet
    # (LEG-58). Kept as an explicit choice at this entrypoint, not a silent
    # default inside the pipeline, so switching to a real provider later is a
    # one-line change here rather than a change to the pipeline's behavior.
    embedding_provider = OfflineEmbeddingProvider(dimensions=EMBEDDING_DIMENSIONS)

    while not _shutting_down:
        # A fresh session per cycle. A long-lived one would eventually hold a
        # stale connection, and a failed job can leave a session unusable.
        session = next(get_session())
        try:
            pipeline = ParseAndChunkPipeline(session, embedding_provider=embedding_provider)
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
    logger.warning(
        "running with OfflineEmbeddingProvider — stored vectors are hash-based "
        "and carry no semantic meaning; retrieval quality cannot be evaluated "
        "until a real embedding model is wired in (LEG-58)"
    )
    run_forever()
    logger.info("ingestion worker stopped")


if __name__ == "__main__":
    main()
