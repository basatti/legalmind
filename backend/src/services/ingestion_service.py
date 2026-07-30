"""The document ingestion pipeline.

Read the stored file → parse it into pages → chunk those pages. Knows nothing
about the queue: it processes one document and either succeeds or raises, and
what to do about a failure is the worker's business.

INCOMPLETE — chunks are counted but not persisted. Storing them needs an
embedding for each one, because DocumentChunk.embedding is NOT NULL, and no
EmbeddingProvider exists yet (LEG-58 built the table but not the provider).
Rather than write placeholder vectors — which would put meaningless numbers in
a table the whole search feature depends on — this stops one step short and
says so. When the provider lands, the store step goes in here and nothing else
in LEG-59 changes.
"""

import logging

from sqlmodel import Session

from chunkers.base import Chunker
from chunkers.fixed_size import FixedSizeChunker
from foundation.storage import StorageBackend, storage
from parsers.base import Parser
from parsers.pdf_parser import PdfParser
from repositories.document_repository import DocumentRepository

logger = logging.getLogger(__name__)


class ParseAndChunkPipeline:
    """Satisfies the worker's Pipeline protocol: parse and chunk one document.

    Takes its session from the caller rather than opening one internally —
    every other service in this codebase is constructed with a session
    (DocumentService, CaseService, ...); a pipeline that quietly opened its own
    connection would be the one exception, cost a second unpooled connection
    per job in production, and be untestable against the standard session
    fixture, since a session it opens itself can never see data committed
    inside a caller's still-open transaction.
    """

    def __init__(
        self,
        session: Session,
        parser: Parser | None = None,
        chunker: Chunker | None = None,
        files: StorageBackend | None = None,
    ) -> None:
        self.documents = DocumentRepository(session)
        self.parser = parser or PdfParser()
        self.chunker = chunker or FixedSizeChunker()
        self.files = files or storage

    def ingest(self, document_id: int) -> int:
        """Parse and chunk one document, returning the chunk count.

        Takes document_id rather than a path because the worker only knows the
        job, and the job only knows which document it is for.
        """
        document = self.documents.get_by_id(document_id)
        if document is None:
            raise ValueError(f"Document {document_id} no longer exists")

        content = self.files.read(document.file_path)
        pages = self.parser.parse(content)
        chunks = self.chunker.chunk(pages)

        logger.info(
            "document %s: %s pages -> %s chunks (not persisted — awaiting LEG-58)",
            document_id,
            len(pages),
            len(chunks),
        )
        return len(chunks)
