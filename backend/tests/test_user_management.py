"""Endpoint tests for /users (LEG-21).

Written after adding `--cov=routers` showed `users_router.py` at 81% with both
endpoint bodies never executed — the two `/users` endpoints had no test that
ran them at all. That matters more here than the percentage suggests: there is
no public signup, so `POST /users` is the only way an account can come into
existence, and `GET /users` is what a partner reads to decide who to assign.

Both are permission-gated, so every case below is tested in both directions —
a role that may, and a role that may not. A permission test that only ever
asserts the allowed path proves nothing about the gate.
"""

from foundation.hashing import hash_password
from foundation.models import Role, User
from tests.conftest import create_user_and_login


def make_user(session, email: str, role: Role) -> User:
    """Create a user directly in the DB without logging them in.

    `create_user_and_login` logs its user in, which replaces the client's
    session cookie. Tests here need target users to exist *without* becoming
    the caller, so they use this instead.
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


VALID_NEW_USER = {
    "email": "new.attorney@example.com",
    "full_name": "New Attorney",
    "temporary_password": "temp12345",
    "role": "attorney",
}


# ---------------------------------------------------------------------------
# POST /users — creation
# ---------------------------------------------------------------------------


def test_admin_creates_a_user(client, session):
    create_user_and_login(client, session, "admin@example.com", Role.ADMIN)

    response = client.post("/users/", json=VALID_NEW_USER)

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new.attorney@example.com"
    assert body["full_name"] == "New Attorney"
    assert body["role"] == "attorney"
    assert body["is_active"] is True
    # Forced on by the service regardless of the request — a temporary password
    # the admin chose is not a password the user has ever consented to.
    assert body["must_change_password"] is True
    # The response model must never carry the hash, whatever the ORM object holds.
    assert "hashed_password" not in body


def test_the_created_user_can_actually_log_in(client, session):
    """The account is usable, not just a row.

    Creation hashes the temporary password on one side of the system and login
    verifies it on the other. Asserting only the 201 would pass even if those
    two disagreed.
    """
    create_user_and_login(client, session, "admin@example.com", Role.ADMIN)
    client.post("/users/", json=VALID_NEW_USER)

    response = client.post(
        "/auth/login",
        json={"email": VALID_NEW_USER["email"], "password": VALID_NEW_USER["temporary_password"]},
    )

    assert response.status_code == 200
    assert response.json()["must_change_password"] is True


def test_duplicate_email_is_rejected(client, session):
    create_user_and_login(client, session, "admin@example.com", Role.ADMIN)
    client.post("/users/", json=VALID_NEW_USER)

    response = client.post("/users/", json=VALID_NEW_USER)

    assert response.status_code == 409


def test_a_weak_temporary_password_is_rejected(client, session):
    """Rejected at validation, before the handler runs — hence 422, not 400."""
    create_user_and_login(client, session, "admin@example.com", Role.ADMIN)

    response = client.post(
        "/users/",
        json={**VALID_NEW_USER, "temporary_password": "short"},
    )

    assert response.status_code == 422


def test_an_attorney_cannot_create_a_user(client, session):
    """The other direction: attorney holds no `user:manage`."""
    create_user_and_login(client, session, "attorney@example.com", Role.ATTORNEY)

    response = client.post("/users/", json=VALID_NEW_USER)

    assert response.status_code == 403


def test_a_partner_cannot_create_a_user(client, session):
    """Partner can *list* users but not create them — the two endpoints have
    different permissions, and reading one is not permission to write."""
    create_user_and_login(client, session, "partner@example.com", Role.PARTNER)

    response = client.post("/users/", json=VALID_NEW_USER)

    assert response.status_code == 403


def test_creating_a_user_while_logged_out_is_401_not_403(client, session):
    """Unauthenticated must not be reported as forbidden — 403 would confirm
    the endpoint exists and is merely gated."""
    response = client.post("/users/", json=VALID_NEW_USER)

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /users — listing
# ---------------------------------------------------------------------------


def test_admin_lists_users(client, session):
    make_user(session, "attorney@example.com", Role.ATTORNEY)
    create_user_and_login(client, session, "admin@example.com", Role.ADMIN)

    response = client.get("/users/")

    assert response.status_code == 200
    emails = [user["email"] for user in response.json()]
    assert "attorney@example.com" in emails
    assert "admin@example.com" in emails


def test_partner_lists_users_through_the_assign_permission(client, session):
    """The `or` branch of `require_permission(USER_MANAGE, CASE_ASSIGN)`.

    Partner holds no `user:manage`; it reaches this endpoint solely through
    `case:assign`, because picking an assignee requires seeing the candidates.
    Without this test the second permission in that call is never exercised and
    could be deleted with the suite still green.
    """
    make_user(session, "attorney@example.com", Role.ATTORNEY)
    create_user_and_login(client, session, "partner@example.com", Role.PARTNER)

    response = client.get("/users/")

    assert response.status_code == 200
    assert "attorney@example.com" in [user["email"] for user in response.json()]


def test_an_attorney_cannot_list_users(client, session):
    create_user_and_login(client, session, "attorney@example.com", Role.ATTORNEY)

    response = client.get("/users/")

    assert response.status_code == 403


def test_a_paralegal_cannot_list_users(client, session):
    create_user_and_login(client, session, "paralegal@example.com", Role.PARALEGAL)

    response = client.get("/users/")

    assert response.status_code == 403


def test_listing_users_while_logged_out_is_401(client, session):
    response = client.get("/users/")

    assert response.status_code == 401
