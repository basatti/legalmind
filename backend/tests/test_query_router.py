"""Tests for the scoped query:ask endpoint (LEG-61).

Retrieval and answer generation aren't built yet (LEG-62/LEG-63) — these
tests only cover the permission guard and the authorized-case-set scoping,
mirroring LEG-41's pattern for case reads.
"""

from foundation.models import Assignment, Case, Role
from tests.conftest import create_user_and_login


def make_case(session, title="Case") -> Case:
    case = Case(title=title, description=None, status="draft")
    session.add(case)
    session.commit()
    session.refresh(case)
    return case


def assign(session, user_id: int, case_id: int) -> None:
    session.add(Assignment(user_id=user_id, case_id=case_id))
    session.commit()


def ask(client, question="What is the deadline?"):
    return client.post("/query/ask", json={"question": question})


# ---------------------------------------------------------------------------
# Permission guard
# ---------------------------------------------------------------------------


def test_unauthenticated_request_is_rejected(client):
    response = ask(client)
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Assignment-scoped roles (Attorney/Paralegal)
# ---------------------------------------------------------------------------


def test_an_attorney_with_no_assigned_cases_gets_a_clean_no_answer(client, session):
    create_user_and_login(client, session, "amy@example.com", Role.ATTORNEY)

    response = ask(client)

    assert response.status_code == 200
    assert response.json()["answer"] is None


def test_an_attorney_with_an_assigned_case_reaches_the_retrieval_seam(client, session):
    """Not implemented yet (LEG-62/63) — but the request must get *past* the
    scoping check to prove case_ids weren't empty, hence 501 not 200/403."""
    case = make_case(session)
    user_id = create_user_and_login(client, session, "amy@example.com", Role.ATTORNEY)
    assign(session, user_id, case.id)

    response = ask(client)

    assert response.status_code == 501


def test_a_paralegal_with_no_assigned_cases_gets_a_clean_no_answer(client, session):
    create_user_and_login(client, session, "priya@example.com", Role.PARALEGAL)

    response = ask(client)

    assert response.status_code == 200
    assert response.json()["answer"] is None


# ---------------------------------------------------------------------------
# Unscoped roles (Partner/Admin) -- case:read:any bypasses scoping entirely,
# even with zero rows in Assignment (LEG-61's core "reject only when
# genuinely empty" requirement).
# ---------------------------------------------------------------------------


def test_a_partner_with_zero_assignment_rows_still_reaches_the_retrieval_seam(client, session):
    create_user_and_login(client, session, "pat@example.com", Role.PARTNER)

    response = ask(client)

    assert response.status_code == 501


def test_an_admin_with_zero_assignment_rows_still_reaches_the_retrieval_seam(client, session):
    create_user_and_login(client, session, "admin@example.com", Role.ADMIN)

    response = ask(client)

    assert response.status_code == 501


# ---------------------------------------------------------------------------
# Request validation
# ---------------------------------------------------------------------------


def test_an_empty_question_is_rejected(client, session):
    create_user_and_login(client, session, "amy@example.com", Role.ATTORNEY)

    response = client.post("/query/ask", json={"question": "   "})

    assert response.status_code == 422
