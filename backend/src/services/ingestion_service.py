"""The document ingestion pipeline.

Read the stored file → parse it into pages → chunk those pages → embed each
chunk → store it. Knows nothing about the queue: it processes one document and
either succeeds or raises, and what to do about a failure is the worker's
business.

Skips re-processing when the file's content hasn't changed since the last
successful run (see hash_content) — ingesting is not free, and most calls into
this happen because *something* changed, not this particular document. `force`
overrides the skip for cases where the bytes are identical but the output
should change anyway, e.g. after moving to a new embedding model.
"""

import logging

from sqlmodel import Session

from chunkers.base import Chunker
from chunkers.fixed_size import FixedSizeChunker
from embeddings.base import EmbeddingProvider
from foundation.hashing import hash_content
from foundation.models import EMBEDDING_DIMENSIONS, DocumentChunk
from foundation.storage import StorageBackend, storage
from parsers.base import Parser
from parsers.pdf_parser import PdfParser
from repositories.document_chunk_repository import DocumentChunkRepository
from repositories.document_repository import DocumentRepository

logger = logging.getLogger(__name__)


class ParseAndChunkPipeline:
    """Satisfies the worker's Pipeline protocol: parse, chunk, embed and store
    one document.

    Takes its session from the caller rather than opening one internally —
    every other service in this codebase is constructed with a session
    (DocumentService, CaseService, ...); a pipeline that quietly opened its own
    connection would be the one exception, cost a second unpooled connection
    per job in production, and be untestable against the standard session
    fixture, since a session it opens itself can never see data committed
    inside a caller's still-open transaction.

    embedding_provider has no default. Parser and Chunker default to their real
    implementations because those *are* the real ones — there is no equivalent
    "real" embedding provider in this codebase yet, only the offline hash-based
    one built for tests and plumbing checks. Defaulting to it here would let a
    caller end up with vectors that carry no meaning without ever deciding to.
    Callers (worker_main.py, tests) choose one explicitly.
    """

    def __init__(
        self,
        session: Session,
        embedding_provider: EmbeddingProvider,
        parser: Parser | None = None,
        chunker: Chunker | None = None,
        files: StorageBackend | None = None,
    ) -> None:
        if embedding_provider.dimensions != EMBEDDING_DIMENSIONS:
            raise ValueError(
                f"Provider produces {embedding_provider.dimensions}-wide vectors, "
                f"but the database column holds {EMBEDDING_DIMENSIONS}"
            )

        self.documents = DocumentRepository(session)
        self.chunks = DocumentChunkRepository(session)
        self.parser = parser or PdfParser()
        self.chunker = chunker or FixedSizeChunker()
        self.embedding_provider = embedding_provider
        self.files = files or storage

    def ingest(self, document_id: int, force: bool = False) -> int:
        """Parse, chunk, embed and store one document.

        Takes document_id rather than a path because the worker only knows the
        job, and the job only knows which document it is for.

        Returns how many chunks were stored, or 0 if the document was skipped
        because its content has not changed since the last successful run.
        """
        document = self.documents.get_by_id(document_id)
        if document is None:
            raise ValueError(f"Document {document_id} no longer exists")

        content = self.files.read(document.file_path)
        content_hash = hash_content(content)

        if not force and document.ingested_content_hash == content_hash:
            logger.info("document %s: unchanged content, skipping", document_id)
            return 0

        pages = self.parser.parse(content)
        chunks = self.chunker.chunk(pages)

        vectors = self.embedding_provider.embed([chunk.text for chunk in chunks])

        rows = [
            DocumentChunk(
                document_id=document_id,
                case_id=document.case_id,
                sequence=chunk.sequence,
                page_number=chunk.page_number,
                text=chunk.text,
                embedding=vector,
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        self.chunks.replace_for_document(document_id, rows)

        # Recorded last, on purpose: if anything above raises, the document
        # keeps no fingerprint and looks not-yet-ingested rather than falsely
        # "done", so a retry after a crash does real work instead of skipping.
        document.ingested_content_hash = content_hash
        self.documents.save(document)

        logger.info(
            "document %s: %s pages -> %s chunks stored",
            document_id,
            len(pages),
            len(rows),
        )
        return len(rows)
