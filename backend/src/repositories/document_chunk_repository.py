from sqlmodel import Session, col, select

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
