from sqlmodel import Session, col, select

from embeddings import Vector
from foundation.authorization import AuthorizedCases, TheseCases
from foundation.models import DocumentChunk


class DocumentChunkRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_many(self, chunks: list[DocumentChunk]) -> list[DocumentChunk]:
        """Insert chunks for a document in one transaction."""
        for chunk in chunks:
            self.session.add(chunk)
        self.session.commit()
        for chunk in chunks:
            self.session.refresh(chunk)
        return chunks

    def get_by_document(self, document_id: int) -> list[DocumentChunk]:
        """Every chunk of a document, in reading order."""
        statement = (
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(col(DocumentChunk.sequence))
        )
        return list(self.session.exec(statement).all())

    def get_by_case(self, case_id: int) -> list[DocumentChunk]:
        statement = select(DocumentChunk).where(DocumentChunk.case_id == case_id)
        return list(self.session.exec(statement).all())

    # LEG-62
    def search(
        self,
        query_vector: Vector,
        within: AuthorizedCases,
        limit: int,
    ) -> list[DocumentChunk]:
        """Filter to authorized cases, then rank the closest `limit` chunks.

        Never search-then-filter: the WHERE narrows the candidate set to cases
        the caller may see *before* the ORDER BY ranks by distance, so a chunk
        outside the user's authorisation can never occupy one of the k slots.

        Takes the authorisation itself rather than a list of ids, so "may see
        everything" and "may see nothing" arrive as different types and the
        branch below cannot be skipped.
        """
        statement = select(DocumentChunk).order_by(
            DocumentChunk.embedding.cosine_distance(query_vector)  # type: ignore[attr-defined]
        )

        if isinstance(within, TheseCases):
            if not within.case_ids:
                return []
            statement = statement.where(col(DocumentChunk.case_id).in_(list(within.case_ids)))

        return list(self.session.exec(statement.limit(limit)).all())

    def delete_by_document(self, document_id: int) -> int:
        """Remove all chunks of a document, returning how many were removed."""
        chunks = self.get_by_document(document_id)
        for chunk in chunks:
            self.session.delete(chunk)
        self.session.commit()
        return len(chunks)

    def replace_for_document(
        self, document_id: int, chunks: list[DocumentChunk]
    ) -> list[DocumentChunk]:
        """Swap a document's chunks for a new set.

        The flush pushes the deletes to the database before the new rows are
        inserted — without it SQLAlchemy emits the inserts first and the unique
        (document_id, sequence) index rejects them. It does not commit, so the
        delete and the insert still succeed or fail together: a re-ingestion can
        never leave a document half-old and half-new.
        """
        for existing in self.get_by_document(document_id):
            self.session.delete(existing)
        self.session.flush()

        for chunk in chunks:
            self.session.add(chunk)
        self.session.commit()
        for chunk in chunks:
            self.session.refresh(chunk)
        return chunks
