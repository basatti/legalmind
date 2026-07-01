from foundation.models import Case
from repositories.case_repository import CaseRepository


class CaseService:
    def __init__(self, repository: CaseRepository):
        self.repository = repository

    def create_case(self, case: Case) -> Case:
        return self.repository.add(case)

    def list_cases(self) -> list[Case]:
        return self.repository.get_all()
