from fastapi import APIRouter, Depends, UploadFile, status
from sqlmodel import Session

from foundation.database import get_session
from foundation.models import User
from foundation.permissions import Permission
from foundation.schemas import DocumentOut
from repositories.assignment_repository import AssignmentRepository
from repositories.case_repository import CaseRepository
from repositories.document_repository import DocumentRepository
from routers.auth_router import require_permission
from services.document_service import DocumentService

router = APIRouter(prefix="/cases/{case_id}/documents", tags=["documents"])


def get_document_service(session: Session = Depends(get_session)) -> DocumentService:
    return DocumentService(
        repository=DocumentRepository(session),
        case_repository=CaseRepository(session),
        assignment_repository=AssignmentRepository(session),
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
    content = await file.read()
    assert file.filename is not None
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
