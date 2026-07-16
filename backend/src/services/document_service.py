import os
from datetime import datetime

from fastapi import HTTPException, status

from foundation.models import Case, Document, User
from foundation.permissions import Permission, has_permission
from foundation.storage import storage
from repositories.assignment_repository import AssignmentRepository
from repositories.case_repository import CaseRepository
from repositories.document_repository import DocumentRepository


class DocumentService:
    ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".png", ".jpg", ".jpeg"}
    MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

    def __init__(
        self,
        repository: DocumentRepository,
        case_repository: CaseRepository,
        assignment_repository: AssignmentRepository,
    ) -> None:
        self.repository = repository
        self.case_repository = case_repository
        self.assignment_repository = assignment_repository

    def _get_case_or_404(self, case_id: int) -> Case:
        case = self.case_repository.get_by_id(case_id)
        if case is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Case not found",
            )
        return case

    def _assert_can_access(self, user: User, case: Case) -> None:
        """Only Partners/Admins (case:read:any) or users assigned to
        this specific case may upload/list its documents."""
        if has_permission(user.role, Permission.CASE_READ_ANY):
            return

        assert user.id is not None
        if not self.assignment_repository.is_assigned(user.id, case.id):  # type: ignore[arg-type]
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not assigned to this case",
            )

    def _validate_file(self, filename: str, content: bytes) -> None:
        extension = os.path.splitext(filename)[1].lower()
        if extension not in self.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File type '{extension}' is not allowed",
            )
        if len(content) > self.MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File exceeds maximum allowed size of 10 MB",
            )

    def upload_document(self, case_id: int, filename: str, content: bytes, user: User) -> Document:
        case = self._get_case_or_404(case_id)
        self._assert_can_access(user, case)
        self._validate_file(filename, content)

        assert user.id is not None
        file_path = storage.save(case_id=case_id, filename=filename, content=content)

        document = Document(
            case_id=case_id,
            filename=filename,
            file_path=file_path,
            uploaded_by=user.id,
            uploaded_at=datetime.now(),
        )
        return self.repository.add(document)

    def list_documents(self, case_id: int, user: User) -> list[Document]:
        case = self._get_case_or_404(case_id)
        self._assert_can_access(user, case)
        return self.repository.get_by_case_id(case_id)
    