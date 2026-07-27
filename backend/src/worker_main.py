"""Entry point for the ingestion worker (LEG-13, stage 5).

The second program. Run it in its own terminal, alongside the API:

    uv run python -m worker_main

It polls the ingestionjob table, does any pending work, and sleeps when there
is nothing to do. Ctrl+C stops it after the current job finishes.
"""

import logging
import signal
import time
from types import FrameType

from sqlmodel import Session

from embeddings import OfflineEmbeddingProvider
from foundation.database import engine
from foundation.models import EMBEDDING_DIMENSIONS
from repositories.document_chunk_repository import DocumentChunkRepository
from repositories.document_repository import DocumentRepository
from repositories.ingestion_job_repository import IngestionJobRepository
from services.ingestion_service import IngestionService
from services.ingestion_worker import IngestionWorker

POLL_SECONDS = 5

logger = logging.getLogger("ingestion-worker")
_running = True


def _request_stop(signum: int, frame: FrameType | None) -> None:
    """Ask the loop to finish after the job it is currently doing."""
    global _running
    logger.info("shutdown requested — will stop after the current job")
    _running = False


def build_worker(session: Session) -> IngestionWorker:
    """Assemble the worker and everything it depends on."""
    return IngestionWorker(
        session=session,
        job_repository=IngestionJobRepository(session),
        ingestion_service=IngestionService(
            document_repository=DocumentRepository(session),
            chunk_repository=DocumentChunkRepository(session),
            embedding_provider=OfflineEmbeddingProvider(dimensions=EMBEDDING_DIMENSIONS),
        ),
    )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)

    logger.info("worker started — polling every %ss, Ctrl+C to stop", POLL_SECONDS)

    while _running:
        with Session(engine) as session:
            processed = build_worker(session).drain()

        if processed:
            logger.info("processed %s job(s)", processed)
        else:
            time.sleep(POLL_SECONDS)

    logger.info("worker stopped")


if __name__ == "__main__":
    main()
