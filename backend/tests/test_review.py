"""Tests for LEG-52: submit -> review -> respond loop.

Every test prints the real response before asserting on it --
run with `pytest -s` to see them.
"""

from foundation.models import Assignment, Case, Role
from tests.conftest import create_user_and_login

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def register_and_login(client, session, email, role) -> int:
    return create_user_and_login(client, session, email, role)


def login(client, email, password="password123") -> None:
    """Switch the client's active session to an already-created user."""
    client.post("/auth/login", json={"email": email, "password": password})


def make_case(session, title="Case", status="draft") -> Case:
    case = Case(title=title, description=None, status=status)
    session.add(case)
    session.commit()
    session.refresh(case)
    return case


def assign(session, user_id: int, case_id: int) -> None:
    session.add(Assignment(user_id=user_id, case_id=case_id))
    session.commit()


# ---------------------------------------------------------------------------
# Full loop: submit -> review -> respond
# ---------------------------------------------------------------------------


def test_full_submit_review_respond_loop(client, session):
    case = make_case(session, title="Loop Case", status="in_progress")
    attorney_id = register_and_login(client, session, "amy@example.com", Role.ATTORNEY)
    assign(session, attorney_id, case.id)

    submit = client.post(
        f"/cases/{case.id}/transition",
        json={"target_status": "submitted_for_review"},
    )
    print(f"\nSUBMIT -> {submit.status_code} {submit.json()}")
    assert submit.status_code == 200
    assert submit.json()["status"] == "submitted_for_review"

    register_and_login(client, session, "pat@example.com", Role.PARTNER)
    review = client.post(
        f"/cases/{case.id}/reviews",
        json={"content": "Please fix the citation on page 2."},
    )
    print(f"REVIEW  -> {review.status_code} {review.json()}")
    assert review.status_code == 201
    root_comment = review.json()
    assert root_comment["parent_id"] is None
    assert root_comment["content"] == "Please fix the citation on page 2."

    case_after_review = client.get(f"/cases/{case.id}")
    print(f"CASE STATUS AFTER REVIEW -> {case_after_review.json()['status']}")
    assert case_after_review.json()["status"] == "under_review"

    login(client, "amy@example.com")
    reply = client.post(
        f"/cases/{case.id}/feedback",
        json={"parent_id": root_comment["id"], "content": "Fixed, see revision."},
    )
    print(f"REPLY   -> {reply.status_code} {reply.json()}")
    assert reply.status_code == 201
    assert reply.json()["parent_id"] == root_comment["id"]
    assert reply.json()["review_id"] == root_comment["review_id"]


# ---------------------------------------------------------------------------
# create_review authorization + state
# ---------------------------------------------------------------------------


def test_attorney_cannot_create_review(client, session):
    case = make_case(session, title="Case", status="submitted_for_review")
    register_and_login(client, session, "amy@example.com", Role.ATTORNEY)

    response = client.post(f"/cases/{case.id}/reviews", json={"content": "Nope."})
    print(f"\nAttorney tried to CREATE REVIEW -> got {response.status_code}")

    assert response.status_code == 403


def test_create_review_rejects_wrong_case_status(client, session):
    case = make_case(session, title="Case", status="draft")
    register_and_login(client, session, "pat@example.com", Role.PARTNER)

    response = client.post(f"/cases/{case.id}/reviews", json={"content": "Too early."})
    print(f"\nReview created on DRAFT case -> got {response.status_code} {response.json()}")

    assert response.status_code == 409


# ---------------------------------------------------------------------------
# respond_to_feedback authorization + validation
# ---------------------------------------------------------------------------


def test_unassigned_attorney_cannot_respond(client, session):
    case = make_case(session, title="Case", status="submitted_for_review")
    register_and_login(client, session, "pat@example.com", Role.PARTNER)
    root = client.post(f"/cases/{case.id}/reviews", json={"content": "Fix this."}).json()

    register_and_login(client, session, "amy@example.com", Role.ATTORNEY)
    response = client.post(
        f"/cases/{case.id}/feedback",
        json={"parent_id": root["id"], "content": "On it."},
    )
    print(f"\nUNASSIGNED Attorney tried to RESPOND -> got {response.status_code}")

    assert response.status_code == 403


def test_respond_rejects_parent_from_another_case(client, session):
    case_a = make_case(session, title="Case A", status="submitted_for_review")
    case_b = make_case(session, title="Case B", status="under_review")

    register_and_login(client, session, "pat@example.com", Role.PARTNER)
    root_on_a = client.post(f"/cases/{case_a.id}/reviews", json={"content": "On case A."}).json()

    attorney_id = register_and_login(client, session, "amy@example.com", Role.ATTORNEY)
    assign(session, attorney_id, case_b.id)

    response = client.post(
        f"/cases/{case_b.id}/feedback",
        json={"parent_id": root_on_a["id"], "content": "Wrong case."},
    )
    print(f"\nCross-case reply -> got {response.status_code} {response.json()}")

    assert response.status_code == 400
