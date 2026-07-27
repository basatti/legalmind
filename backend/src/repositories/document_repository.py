from sqlmodel import Session, select

from foundation.models import Document


class DocumentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, document: Document) -> Document:
        self.session.add(document)
        self.session.commit()
        self.session.refresh(document)
        return document

    def save(self, document: Document) -> Document:
        """Persist changes to an existing document.

        Identical mechanism to add() — SQLAlchemy works out insert vs update on
        its own — but the name says what the caller means.
        """
        return self.add(document)

    def get_by_id(self, document_id: int) -> Document | None:
        return self.session.get(Document, document_id)

    def get_by_case_id(self, case_id: int) -> list[Document]:
        statement = select(Document).where(Document.case_id == case_id)
        return list(self.session.exec(statement).all())
