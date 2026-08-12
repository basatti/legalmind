"""Endpoint tests for POST /cases/{case_id}/assign (LEG-30).

Written after `--cov=routers` showed `case_router.py:125` — the body of the
assign endpoint — never executing. `CaseService.assign_user` was already
covered through service-level tests, so what was missing is specifically the
HTTP wiring: the permission gate, the path parameter, and that the service's
four failure modes surface as the right status codes rather than 500s.

Assignment is the hinge of the whole authorization model — it is what turns
"attorney" into "attorney who may read case 7". Every case below is therefore
tested in both directions.
"""

from foundation.hashing import hash_password
from foundation.models import Role, User
from tests.conftest import create_user_and_login


def make_user(session, email: str, role: Role) -> User:
    """Create an assignable user without logging them in.

    `create_user_and_login` would replace the caller's session cookie, and
    these tests need a target that is not the caller.
    """
    user = User(
        email=email,
        full_name="Target User",
        hashed_password=hash_password("password123"),
        role=role,
        must_change_password=False,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def create_case(client, title: str = "Assignment Case") -> int:
    response = client.post("/cases/", json={"title": title, "description": "A case"})
    assert response.status_code == 201
    case_id: int = response.json()["id"]
    return case_id


# ---------------------------------------------------------------------------
# The permitted path
# ---------------------------------------------------------------------------


def test_partner_assigns_an_attorney(client, session):
    attorney = make_user(session, "attorney@example.com", Role.ATTORNEY)
    create_user_and_login(client, session, "partner@example.com", Role.PARTNER)
    case_id = create_case(client)

    response = client.post(f"/cases/{case_id}/assign", json={"user_id": attorney.id})

    assert response.status_code == 201
    body = response.json()
    assert body["case_id"] == case_id
    assert body["user_id"] == attorney.id


def test_partner_assigns_a_paralegal(client, session):
    """Both assignable roles, not just the first one — the service checks
    membership of a two-element tuple, and a test of only one leg would pass
    against a check that had silently narrowed to it."""
    paralegal = make_user(session, "paralegal@example.com", Role.PARALEGAL)
    create_user_and_login(client, session, "partner@example.com", Role.PARTNER)
    case_id = create_case(client)

    response = client.post(f"/cases/{case_id}/assign", json={"user_id": paralegal.id})

    assert response.status_code == 201


def test_admin_can_also_assign(client, session):
    """Admin reaches this through the same `case:assign` permission partner
    uses; the docstring on the endpoint says Partner/Admin and both are real."""
    attorney = make_user(session, "attorney@example.com", Role.ATTORNEY)
    create_user_and_login(client, session, "admin@example.com", Role.ADMIN)
    case_id = create_case(client)

    response = client.post(f"/cases/{case_id}/assign", json={"user_id": attorney.id})

    assert response.status_code == 201


# ---------------------------------------------------------------------------
# The service's failure modes, as seen over HTTP
# ---------------------------------------------------------------------------


def test_assigning_a_partner_is_rejected(client, session):
    """Only attorneys and paralegals do case work. Assigning a partner or an
    admin would silently widen their read scope through the assignment table."""
    other_partner = make_user(session, "other.partner@example.com", Role.PARTNER)
    create_user_and_login(client, session, "partner@example.com", Role.PARTNER)
    case_id = create_case(client)

    response = client.post(f"/cases/{case_id}/assign", json={"user_id": other_partner.id})

    assert response.status_code == 400


def test_assigning_to_a_missing_case_is_404(client, session):
    attorney = make_user(session, "attorney@example.com", Role.ATTORNEY)
    create_user_and_login(client, session, "partner@example.com", Role.PARTNER)

    response = client.post("/cases/999999/assign", json={"user_id": attorney.id})

    assert response.status_code == 404


def test_assigning_a_missing_user_is_404(client, session):
    create_user_and_login(client, session, "partner@example.com", Role.PARTNER)
    case_id = create_case(client)

    response = client.post(f"/cases/{case_id}/assign", json={"user_id": 999999})

    assert response.status_code == 404


def test_assigning_the_same_user_twice_is_409(client, session):
    """Idempotency is deliberately *not* the contract here — a duplicate is
    reported rather than silently absorbed, so a double-click in the UI does
    not look like it created a second assignment."""
    attorney = make_user(session, "attorney@example.com", Role.ATTORNEY)
    create_user_and_login(client, session, "partner@example.com", Role.PARTNER)
    case_id = create_case(client)
    client.post(f"/cases/{case_id}/assign", json={"user_id": attorney.id})

    response = client.post(f"/cases/{case_id}/assign", json={"user_id": attorney.id})

    assert response.status_code == 409


# ---------------------------------------------------------------------------
# The forbidden direction
# ---------------------------------------------------------------------------


def test_an_attorney_cannot_assign(client, session):
    """The gate that matters: without it an attorney could assign themselves
    to any case and read it — self-service authorization."""
    target = make_user(session, "other.attorney@example.com", Role.ATTORNEY)
    admin_id = create_user_and_login(client, session, "admin@example.com", Role.ADMIN)
    case_id = create_case(client)
    assert admin_id is not None

    create_user_and_login(client, session, "attorney@example.com", Role.ATTORNEY)
    response = client.post(f"/cases/{case_id}/assign", json={"user_id": target.id})

    assert response.status_code == 403


def test_a_paralegal_cannot_assign(client, session):
    target = make_user(session, "attorney@example.com", Role.ATTORNEY)
    create_user_and_login(client, session, "admin@example.com", Role.ADMIN)
    case_id = create_case(client)

    create_user_and_login(client, session, "paralegal@example.com", Role.PARALEGAL)
    response = client.post(f"/cases/{case_id}/assign", json={"user_id": target.id})

    assert response.status_code == 403


def test_assigning_while_logged_out_is_401(client, session):
    target = make_user(session, "attorney@example.com", Role.ATTORNEY)
    create_user_and_login(client, session, "admin@example.com", Role.ADMIN)
    case_id = create_case(client)
    client.post("/auth/logout")

    response = client.post(f"/cases/{case_id}/assign", json={"user_id": target.id})

    assert response.status_code == 401
