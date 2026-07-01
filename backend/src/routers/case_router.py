from fastapi import APIRouter

from foundation.models import Case
from repositories.case_repository import CaseRepository
from services.case_service import CaseService

router = APIRouter(prefix="/cases", tags=["cases"])
service = CaseService(CaseRepository())


@router.get("/")
def list_cases() -> list[Case]:
    return service.list_cases()


@router.post("/")
def create_case(case: Case) -> Case:
    return service.create_case(case)
