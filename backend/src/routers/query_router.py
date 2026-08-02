from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from foundation.database import get_session
from foundation.models import User
from foundation.permissions import Permission
from foundation.schemas import QueryAskRequest, QueryAskResponse
from repositories.assignment_case_reader import AssignmentCaseReader
from repositories.assignment_repository import AssignmentRepository
from routers.auth_router import require_permission
from services.rag_service import RagService

router = APIRouter(prefix="/query", tags=["query"])


def get_rag_service(session: Session = Depends(get_session)) -> RagService:
    return RagService(case_reader=AssignmentCaseReader(AssignmentRepository(session)))


@router.post("/ask")
def ask(
    data: QueryAskRequest,
    service: RagService = Depends(get_rag_service),
    user: User = Depends(
        require_permission(Permission.CASE_READ_ANY, Permission.CASE_READ_ASSIGNED)
    ),
) -> QueryAskResponse:
    try:
        return service.ask(data.question, user)
    except NotImplementedError as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=str(exc),
        ) from exc
