from fastapi import APIRouter, Depends, status
from sqlmodel import Session

from foundation.database import get_session
from foundation.models import Case, User
from foundation.schemas import CaseCreateRequest, CaseResponse, CaseUpdateRequest
from repositories.case_repository import CaseRepository
from routers.auth_router import current_user
from services.case_service import CaseService

router = APIRouter(prefix="/cases", tags=["cases"])


def get_case_service(session: Session = Depends(get_session)) -> CaseService:
    return CaseService(CaseRepository(session))


@router.get("/", response_model=list[CaseResponse])
def list_cases(
    service: CaseService = Depends(get_case_service),
    _user: User = Depends(current_user),
) -> list[Case]:
    return service.list_cases()


@router.post("/", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
def create_case(
    data: CaseCreateRequest,
    service: CaseService = Depends(get_case_service),
    _user: User = Depends(current_user),
) -> Case:
    return service.create_case(data)


@router.get("/{case_id}", response_model=CaseResponse)
def get_case(
    case_id: int,
    service: CaseService = Depends(get_case_service),
    _user: User = Depends(current_user),
) -> Case:
    return service.get_case(case_id)


@router.patch("/{case_id}", response_model=CaseResponse)
def update_case(
    case_id: int,
    data: CaseUpdateRequest,
    service: CaseService = Depends(get_case_service),
    _user: User = Depends(current_user),
) -> Case:
    return service.update_case(case_id, data)
