"""Runs the ingestion pipeline for a single document (LEG-13).

Ties the four stages together: parse -> chunk -> embed -> store. Knows nothing
about queues or HTTP — it does one document, start to finish, and something else
decides when to call it.
"""

from chunkers import Chunker, FixedSizeChunker
from embeddings import EmbeddingProvider
from foundation.hashing import hash_content
from foundation.models import EMBEDDING_DIMENSIONS, DocumentChunk
from foundation.storage import StorageBackend, storage
from parsers import get_parser_for, is_supported
from repositories.document_chunk_repository import DocumentChunkRepository
from repositories.document_repository import DocumentRepository


class IngestionError(Exception):
    """Raised when a document cannot be ingested."""


class IngestionService:
    def __init__(
        self,
        document_repository: DocumentRepository,
        chunk_repository: DocumentChunkRepository,
        embedding_provider: EmbeddingProvider,
        chunker: Chunker | None = None,
        storage_backend: StorageBackend | None = None,
    ) -> None:
        if embedding_provider.dimensions != EMBEDDING_DIMENSIONS:
            raise IngestionError(
                f"Provider produces {embedding_provider.dimensions}-wide vectors, "
                f"but the database column holds {EMBEDDING_DIMENSIONS}"
            )

        self.document_repository = document_repository
        self.chunk_repository = chunk_repository
        self.embedding_provider = embedding_provider
        self.chunker = chunker or FixedSizeChunker()
        self.storage = storage_backend or storage

    def ingest_document(self, document_id: int, force: bool = False) -> int:
        """Parse, chunk, embed and store one document.

        Returns how many chunks were stored, or 0 if the document was skipped
        because its content has not changed since the last successful run.
        """
        document = self.document_repository.get_by_id(document_id)
        if document is None:
            raise IngestionError(f"Document {document_id} not found")

        if not is_supported(document.filename):
            raise IngestionError(f"No parser can handle '{document.filename}'")

        content = self.storage.read(document.file_path)
        content_hash = hash_content(content)

        if not force and document.ingested_content_hash == content_hash:
            # Identical bytes to the last successful run, so the chunks already
            # in the database are still correct. Nothing to redo.
            return 0

        pages = get_parser_for(document.filename).parse(content)
        chunks = self.chunker.chunk(pages)

        if not chunks:
            raise IngestionError(f"Document {document_id} produced no chunks")

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
        self.chunk_repository.replace_for_document(document_id, rows)

        # Recorded last, on purpose — see below.
        document.ingested_content_hash = content_hash
        self.document_repository.save(document)

        return len(rows)
