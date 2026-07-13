"""Case business logic with assignment-scoped access (LEG-40)."""

from fastapi import HTTPException, status

from foundation.case_state_machine import CaseStateMachine
from foundation.models import Case, CaseStatus, User
from foundation.permissions import Permission, has_permission
from foundation.schemas import CaseCreateRequest, CaseUpdateRequest
from repositories.assignment_repository import AssignmentRepository
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
    def __init__(
        self,
        repository: CaseRepository,
        assignment_repository: AssignmentRepository,
    ) -> None:
        self.repository = repository
        self.assignment_repository = assignment_repository
        self.state_machine = CaseStateMachine()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _assert_can_read(self, user: User, case: Case) -> None:
        """Raise 403 if user can't read this specific case.

        Partners and Admins have case:read:any — they bypass the check.
        Attorneys and Paralegals have case:read:assigned — they must be
        in the Assignment table for this case.

        This is the core assignment-scoped access check (LEG-40).
        """
        if has_permission(user.role, Permission.CASE_READ_ANY):
            return  # Partner/Admin — can read anything

        # Attorney/Paralegal — must be assigned
        assert user.id is not None
        if not self.assignment_repository.is_assigned(user.id, case.id):  # type: ignore[arg-type]
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not assigned to this case",
            )

    def _assert_can_edit(self, user: User, case: Case) -> None:
        """Raise 403 if user can't edit this specific case."""
        if has_permission(user.role, Permission.CASE_EDIT_ANY):
            return  # Partner/Admin

        assert user.id is not None
        if not self.assignment_repository.is_assigned(user.id, case.id):  # type: ignore[arg-type]
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not assigned to this case",
            )

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create_case(self, data: CaseCreateRequest) -> Case:
        case = Case(title=data.title, description=data.description)
        return self.repository.add(case)

    def list_cases(self, user: User) -> list[Case]:
        """Return cases the user is allowed to see.

        Partners/Admins → all cases (case:read:any).
        Attorneys/Paralegals → only assigned cases (case:read:assigned).
        """
        if has_permission(user.role, Permission.CASE_READ_ANY):
            return self.repository.get_all()

        assert user.id is not None
        case_ids = self.assignment_repository.get_case_ids_for_user(user.id)
        return self.repository.get_by_ids(case_ids)

    def get_case(self, case_id: int, user: User) -> Case:
        case = self.repository.get_by_id(case_id)
        if case is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Case not found",
            )
        self._assert_can_read(user, case)
        return case

    def update_case(self, case_id: int, data: CaseUpdateRequest, user: User) -> Case:
        case = self.repository.get_by_id(case_id)
        if case is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Case not found",
            )
        self._assert_can_edit(user, case)
        if data.title is not None:
            case.title = data.title
        if data.description is not None:
            case.description = data.description
        return self.repository.update(case)

    def transition_status(self, case_id: int, target_status: CaseStatus, user: User) -> Case:
        case = self.repository.get_by_id(case_id)
        if case is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Case not found",
            )
        self._assert_can_read(user, case)

        if not self.state_machine.can_transition(case.status, target_status):
            allowed = self.state_machine.allowed_next(case.status)
            raise IllegalTransitionError(case.status, target_status, allowed)

        case.status = target_status
        return self.repository.update(case)
