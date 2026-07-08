from fastapi import HTTPException, status

from foundation.models import Case
from foundation.schemas import CaseCreateRequest, CaseUpdateRequest
from repositories.case_repository import CaseRepository


class CaseService:
    def __init__(self, repository: CaseRepository):
        self.repository = repository

    def create_case(self, data: CaseCreateRequest) -> Case:
        case = Case(title=data.title, description=data.description)
        return self.repository.add(case)

    def list_cases(self) -> list[Case]:
        return self.repository.get_all()

    def get_case(self, case_id: int) -> Case:
        case = self.repository.get_by_id(case_id)
        if case is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Case not found",
            )
        return case

    def update_case(self, case_id: int, data: CaseUpdateRequest) -> Case:
        case = self.get_case(case_id)

        if data.title is not None:
            case.title = data.title
        if data.description is not None:
            case.description = data.description

        return self.repository.update(case)
