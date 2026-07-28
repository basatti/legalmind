import pytest

from foundation.models import Role
from tests.conftest import create_user_and_login

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def register_and_login(client, session, email="user@example.com"):
    # CRUD/FSM tests check case behavior, not authorization
    create_user_and_login(client, session, email, Role.ADMIN)
    return client


def create_case(client, title="Test Case", description="A test case"):
    response = client.post(
        "/cases/",
        json={"title": title, "description": description},
    )
    return response


# ---------------------------------------------------------------------------
# CRUD tests
# ---------------------------------------------------------------------------


def test_create_case(client, session):
    register_and_login(client, session)
    response = create_case(client)
    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Test Case"
    assert body["status"] == "draft"


def test_list_cases(client, session):
    register_and_login(client, session)
    create_case(client, title="Case A")
    create_case(client, title="Case B")

    response = client.get("/cases/")
    assert response.status_code == 200
    titles = [c["title"] for c in response.json()]
    assert "Case A" in titles
    assert "Case B" in titles


def test_get_case_by_id(client, session):
    register_and_login(client, session)
    created = create_case(client).json()

    response = client.get(f"/cases/{created['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_get_nonexistent_case_returns_404(client, session):
    register_and_login(client, session)
    response = client.get("/cases/99999")
    assert response.status_code == 404


def test_update_case(client, session):
    register_and_login(client, session)
    created = create_case(client).json()

    response = client.patch(
        f"/cases/{created['id']}",
        json={"title": "Updated Title"},
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Updated Title"


# ---------------------------------------------------------------------------
# Legal transitions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "from_status,target_status",
    [
        ("draft", "in_progress"),
        ("in_progress", "submitted_for_review"),
        ("submitted_for_review", "under_review"),
        ("under_review", "revisions_requested"),
        ("under_review", "closed"),
        ("revisions_requested", "in_progress"),
    ],
)
def test_legal_transition_succeeds(client, session, from_status, target_status):
    from foundation.models import Case

    register_and_login(client, session)
    case = Case(title="Case", description=None, status=from_status)
    session.add(case)
    session.commit()
    session.refresh(case)

    response = client.post(
        f"/cases/{case.id}/transition",
        json={"target_status": target_status},
    )
    assert response.status_code == 200
    assert response.json()["status"] == target_status


# ---------------------------------------------------------------------------
# Illegal transitions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "from_status,target_status",
    [
        ("draft", "closed"),
        ("draft", "under_review"),
        ("draft", "submitted_for_review"),
        ("in_progress", "draft"),
        ("closed", "draft"),
        ("closed", "in_progress"),
        ("under_review", "draft"),
    ],
)
def test_illegal_transition_rejected(client, session, from_status, target_status):
    from foundation.models import Case

    register_and_login(client, session)
    case = Case(title="Case", description=None, status=from_status)
    session.add(case)
    session.commit()
    session.refresh(case)

    response = client.post(
        f"/cases/{case.id}/transition",
        json={"target_status": target_status},
    )
    assert response.status_code == 409
    assert "Cannot transition" in response.json()["detail"]


def test_transition_on_nonexistent_case_returns_404(client, session):
    register_and_login(client, session)
    response = client.post(
        "/cases/99999/transition",
        json={"target_status": "in_progress"},
    )
    assert response.status_code == 404


def test_transition_requires_authentication(client):
    response = client.post(
        "/cases/1/transition",
        json={"target_status": "in_progress"},
    )
    assert response.status_code == 401
