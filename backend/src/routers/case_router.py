from fastapi import APIRouter, Depends
from sqlmodel import Session

from foundation.database import get_session
from foundation.models import Case, User
from repositories.case_repository import CaseRepository
from routers.auth_router import current_user
from services.case_service import CaseService

router = APIRouter(prefix="/cases", tags=["cases"])


def get_case_service(session: Session = Depends(get_session)) -> CaseService:
    return CaseService(CaseRepository(session))


@router.get("/")
def list_cases(
    service: CaseService = Depends(get_case_service),
    _user: User = Depends(current_user),
) -> list[Case]:
    return service.list_cases()


@router.post("/")
def create_case(
    case: Case,
    service: CaseService = Depends(get_case_service),
    _user: User = Depends(current_user),
) -> Case:
    return service.create_case(case)
