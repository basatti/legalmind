from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from foundation.database import get_session
from foundation.models import Case, User
from foundation.schemas import (
    CaseCreateRequest,
    CaseTransitionRequest,
    CaseUpdateRequest,
)
from repositories.case_repository import CaseRepository
from routers.auth_router import current_user
from services.case_service import CaseService, IllegalTransitionError

router = APIRouter(prefix="/cases", tags=["cases"])


def get_case_service(session: Session = Depends(get_session)) -> CaseService:
    return CaseService(CaseRepository(session))


@router.get("/")
def list_cases(
    service: CaseService = Depends(get_case_service),
    _user: User = Depends(current_user),
) -> list[Case]:
    return service.list_cases()


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_case(
    data: CaseCreateRequest,
    service: CaseService = Depends(get_case_service),
    _user: User = Depends(current_user),
) -> Case:
    return service.create_case(data)


@router.get("/{case_id}")
def get_case(
    case_id: int,
    service: CaseService = Depends(get_case_service),
    _user: User = Depends(current_user),
) -> Case:
    return service.get_case(case_id)


@router.patch("/{case_id}")
def update_case(
    case_id: int,
    data: CaseUpdateRequest,
    service: CaseService = Depends(get_case_service),
    _user: User = Depends(current_user),
) -> Case:
    return service.update_case(case_id, data)


@router.post("/{case_id}/transition")
def transition_case(
    case_id: int,
    data: CaseTransitionRequest,
    service: CaseService = Depends(get_case_service),
    _user: User = Depends(current_user),
) -> Case:
    try:
        return service.transition_status(case_id, data.target_status)
    except IllegalTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
