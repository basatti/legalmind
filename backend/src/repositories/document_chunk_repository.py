from sqlmodel import Session, col, select

from embeddings import Vector
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

    #Leg 62 
    def search(
        self,
        question_vector: Vector,
        authorized_case_ids: list[int] | None,
        top_k: int,
    ) -> list[DocumentChunk]:
        """Filter to authorized cases, then rank top-k within that set.

        Never search-then-filter: the WHERE narrows the candidate set to
        cases the caller is allowed to see *before* the ORDER BY ranks by
        distance, so a chunk outside the user's assignments can never
        occupy one of the k slots.

        authorized_case_ids:
          - None -> no restriction (e.g. Partner/Admin with case:read:any)
          - []   -> restricted, and authorized for nothing -> no results
          - [.., ..] -> restricted to exactly these cases
        """
        if authorized_case_ids is not None and not authorized_case_ids:
            return []

        statement = select(DocumentChunk).order_by(
            DocumentChunk.embedding.cosine_distance(question_vector)
        )
        if authorized_case_ids is not None:
            statement = statement.where(col(DocumentChunk.case_id).in_(authorized_case_ids))
        statement = statement.limit(top_k)

        return list(self.session.exec(statement).all())

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
