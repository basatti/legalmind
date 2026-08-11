from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlmodel import Session

from foundation.database import get_session
from foundation.models import User
from foundation.permissions import Permission
from foundation.schemas import DocumentOut
from repositories.assignment_repository import AssignmentRepository
from repositories.case_repository import CaseRepository
from repositories.document_repository import DocumentRepository
from repositories.ingestion_job_repository import IngestionJobRepository
from routers.auth_router import require_permission
from services.document_service import DocumentService

router = APIRouter(prefix="/cases/{case_id}/documents", tags=["documents"])


def get_document_service(session: Session = Depends(get_session)) -> DocumentService:
    return DocumentService(
        repository=DocumentRepository(session),
        case_repository=CaseRepository(session),
        assignment_repository=AssignmentRepository(session),
        jobs=IngestionJobRepository(session),
    )


@router.post("/", status_code=status.HTTP_201_CREATED)
async def upload_document(
    case_id: int,
    file: UploadFile,
    service: DocumentService = Depends(get_document_service),
    user: User = Depends(
        require_permission(Permission.CASE_EDIT_ANY, Permission.CASE_EDIT_ASSIGNED)
    ),
) -> DocumentOut:
    if not file.filename:
        # Was an `assert`, which made a multipart part with no filename a 500
        # rather than a 400 — and asserts are stripped entirely under `python -O`.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload is missing a filename",
        )

    # Reject on the declared size before reading. The service checks the real
    # length too, and that check is the authoritative one — but it runs after
    # the whole body is already in memory, so a large upload could exhaust the
    # container before validation ever got a say.
    if file.size is not None and file.size > DocumentService.MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File exceeds maximum allowed size of 10 MB",
        )

    content = await file.read()
    document = service.upload_document(case_id, file.filename, content, user)
    return DocumentOut(
        id=document.id,  # type: ignore[arg-type]
        case_id=document.case_id,
        filename=document.filename,
        uploaded_by=document.uploaded_by,
        uploaded_at=document.uploaded_at,
    )


@router.get("/")
def list_documents(
    case_id: int,
    service: DocumentService = Depends(get_document_service),
    user: User = Depends(
        require_permission(Permission.CASE_READ_ANY, Permission.CASE_READ_ASSIGNED)
    ),
) -> list[DocumentOut]:
    documents = service.list_documents(case_id, user)
    return [
        DocumentOut(
            id=doc.id,  # type: ignore[arg-type]
            case_id=doc.case_id,
            filename=doc.filename,
            uploaded_by=doc.uploaded_by,
            uploaded_at=doc.uploaded_at,
        )
        for doc in documents
    ]
