"""Tests for the concrete CaseReader backed by Assignment (LEG-61/64)."""

from foundation.authorization import AllCases, TheseCases
from foundation.hashing import hash_password
from foundation.models import Assignment, Case, Role, User
from repositories.assignment_case_reader import AssignmentCaseReader
from repositories.assignment_repository import AssignmentRepository


def make_user(session, role: Role, email="u@example.com") -> User:
    user = User(
        email=email,
        full_name="Test User",
        hashed_password=hash_password("password123"),
        role=role,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def make_case(session, title="Case") -> Case:
    case = Case(title=title, description=None, status="draft")
    session.add(case)
    session.commit()
    session.refresh(case)
    return case


def reader(session) -> AssignmentCaseReader:
    return AssignmentCaseReader(AssignmentRepository(session))


def test_partner_gets_all_cases_despite_zero_assignment_rows(session):
    partner = make_user(session, Role.PARTNER)

    result = reader(session).authorized_cases(partner)

    assert result == AllCases()


def test_admin_gets_all_cases_despite_zero_assignment_rows(session):
    admin = make_user(session, Role.ADMIN)

    result = reader(session).authorized_cases(admin)

    assert result == AllCases()


def test_attorney_with_no_assignments_gets_an_empty_these_cases(session):
    attorney = make_user(session, Role.ATTORNEY)

    result = reader(session).authorized_cases(attorney)

    assert result == TheseCases(frozenset())


def test_attorney_gets_exactly_their_assigned_case_ids(session):
    attorney = make_user(session, Role.ATTORNEY)
    case_a = make_case(session, "A")
    case_b = make_case(session, "B")
    make_case(session, "C — not assigned")

    session.add(Assignment(user_id=attorney.id, case_id=case_a.id))
    session.add(Assignment(user_id=attorney.id, case_id=case_b.id))
    session.commit()

    result = reader(session).authorized_cases(attorney)

    assert result == TheseCases(frozenset({case_a.id, case_b.id}))
