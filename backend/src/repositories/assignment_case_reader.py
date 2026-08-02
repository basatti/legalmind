"""Concrete CaseReader backed by the permission matrix + Assignment table.

Same scoping CaseService.list_cases uses (LEG-40), expressed as an
AuthorizedCases value (LEG-64) instead of a branch the caller has to repeat.
"""

from foundation.authorization import AllCases, AuthorizedCases, TheseCases
from foundation.models import User
from foundation.permissions import Permission, has_permission
from repositories.assignment_repository import AssignmentRepository


class AssignmentCaseReader:
    def __init__(self, assignment_repository: AssignmentRepository) -> None:
        self.assignment_repository = assignment_repository

    def authorized_cases(self, user: User) -> AuthorizedCases:
        if has_permission(user.role, Permission.CASE_READ_ANY):
            return AllCases()
        assert user.id is not None
        case_ids = self.assignment_repository.get_case_ids_for_user(user.id)
        return TheseCases(frozenset(case_ids))
