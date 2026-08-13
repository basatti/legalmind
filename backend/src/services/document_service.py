import os
from datetime import datetime

from fastapi import HTTPException, status

from foundation.models import Case, Document, User
from foundation.permissions import Permission, has_permission
from foundation.storage import storage
from parsers import content_matches_extension, is_supported, supported_extensions
from repositories.assignment_repository import AssignmentRepository
from repositories.case_repository import CaseRepository
from repositories.document_repository import DocumentRepository
from repositories.ingestion_job_repository import IngestionJobRepository


class DocumentService:
    MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

    def __init__(
        self,
        repository: DocumentRepository,
        case_repository: CaseRepository,
        assignment_repository: AssignmentRepository,
        jobs: IngestionJobRepository,
    ) -> None:
        self.repository = repository
        self.case_repository = case_repository
        self.assignment_repository = assignment_repository
        self.jobs = jobs

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
        # Ask the parser registry rather than keeping a second list here. This
        # used to hold its own set — .doc, .docx, .png, .jpg — while the
        # registry only knows .pdf, so a Word file uploaded cleanly, appeared
        # on the case, and then died in the worker four retries later where
        # nobody was looking. The user was never told.
        #
        # Registering a new parser now widens the upload gate on its own, which
        # is the point: these two can no longer drift apart.
        if not is_supported(filename):
            extension = os.path.splitext(filename)[1].lower()
            accepted = ", ".join(supported_extensions())
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File type '{extension}' is not allowed. Accepted: {accepted}",
            )
        if len(content) > self.MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File exceeds maximum allowed size of 10 MB",
            )

        # The check above reads the file's name; this one reads the file. They
        # are unrelated facts -- renaming a document takes two seconds and
        # changes nothing inside it -- and until now only the name was ever
        # consulted. A Word file renamed to .pdf was accepted, stored, queued,
        # and died in the worker hours later, by which time the only person who
        # could have fixed it had long since seen a green tick and moved on.
        #
        # Deliberately after the extension check, not before: "we don't accept
        # .docx" is a more useful thing to hear than "these bytes aren't a PDF"
        # when the file is honestly named.
        if not content_matches_extension(filename, content):
            extension = os.path.splitext(filename)[1].lower()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"This file's contents are not a {extension.lstrip('.').upper()}. "
                    "It may have been renamed from another format."
                ),
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
        saved = self.repository.add(document)

        # Queue the ingestion rather than doing it here. Parsing and embedding a
        # 500-page PDF takes over a minute — far longer than an HTTP request
        # should hold a connection open. The upload returns as soon as the row
        # exists; a worker picks the job up independently.
        assert saved.id is not None
        self.jobs.enqueue(saved.id)
        return saved

    def list_documents(self, case_id: int, user: User) -> list[Document]:
        case = self._get_case_or_404(case_id)
        self._assert_can_access(user, case)
        return self.repository.get_by_case_id(case_id)
