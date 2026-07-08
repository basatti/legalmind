from fastapi import HTTPException, status

from foundation.case_state_machine import CaseStateMachine
from foundation.models import Case, CaseStatus
from foundation.schemas import CaseCreateRequest, CaseUpdateRequest
from repositories.case_repository import CaseRepository


class IllegalTransitionError(Exception):
    """Raised when a case status transition violates the state machine."""

    def __init__(self, current: CaseStatus, target: CaseStatus, allowed: list[CaseStatus]):
        self.current = current
        self.target = target
        self.allowed = allowed
        allowed_str = [s.value for s in allowed] if allowed else "none (terminal state)"
        super().__init__(
            f"Cannot transition case from '{current.value}' to '{target.value}'. "
            f"Allowed transitions from '{current.value}': {allowed_str}"
        )


class CaseService:
    def __init__(self, repository: CaseRepository):
        self.repository = repository
        self.state_machine = CaseStateMachine()

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

    def transition_status(self, case_id: int, target_status: CaseStatus) -> Case:
        case = self.get_case(case_id)

        if not self.state_machine.can_transition(case.status, target_status):
            allowed = self.state_machine.allowed_next(case.status)
            raise IllegalTransitionError(case.status, target_status, allowed)

        case.status = target_status
        return self.repository.update(case)
