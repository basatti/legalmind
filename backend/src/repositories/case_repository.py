from foundation.models import Case


class CaseRepository:
    def __init__(self):
        self._cases: list[Case] = []

    def add(self, case: Case) -> Case:
        self._cases.append(case)
        return case

    def get_all(self) -> list[Case]:
        return self._cases
