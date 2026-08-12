"""What happens at bcrypt's edges — found by driving the running stack.

`POST /auth/login` with a password over 72 bytes returned **500 for an account
that exists and 401 for one that does not**. bcrypt 5 raises rather than
truncating, and nothing caught it. That status-code difference is a
user-enumeration oracle, which is precisely what `AuthService.login` returns an
identical error for a wrong email and a wrong password to prevent.

Unit tests could not have found it: every test password was a sensible length.
"""

import pytest

from foundation.hashing import hash_password, verify_password
from foundation.models import Role, User
from foundation.schemas import MAX_PASSWORD_BYTES
from tests.conftest import create_user_and_login

OVER_LIMIT = "a" * MAX_PASSWORD_BYTES + "1"
AT_LIMIT = "a" * (MAX_PASSWORD_BYTES - 1) + "1"


def make_user(session, email: str = "victim@example.com") -> User:
    user = User(
        email=email,
        full_name="Password Limits",
        hashed_password=hash_password("password123"),
        role=Role.ADMIN,
        must_change_password=False,
    )
    session.add(user)
    session.commit()
    return user


# ---------------------------------------------------------------------------
# verify_password fails closed
# ---------------------------------------------------------------------------


def test_an_over_long_password_is_wrong_not_an_error():
    assert verify_password(OVER_LIMIT, hash_password("password123")) is False


def test_a_password_at_the_limit_still_works():
    """The boundary is usable, not merely safe — 72 bytes must still verify."""
    assert verify_password(AT_LIMIT, hash_password(AT_LIMIT)) is True


def test_a_hash_that_is_not_a_hash_is_wrong_not_an_error():
    """A row seeded by hand with the wrong column value would otherwise 500
    forever for that one account, singling it out from every other."""
    assert verify_password("password123", "not-a-bcrypt-hash") is False


def test_an_empty_hash_is_wrong_not_an_error():
    assert verify_password("password123", "") is False


# ---------------------------------------------------------------------------
# The oracle itself, over HTTP
# ---------------------------------------------------------------------------


def test_login_with_an_over_long_password_is_401(client, session):
    make_user(session)

    response = client.post(
        "/auth/login", json={"email": "victim@example.com", "password": OVER_LIMIT}
    )

    assert response.status_code == 401


def test_an_existing_and_a_missing_account_are_indistinguishable(client, session):
    """The actual defect. Before the fix these were 500 and 401, so one request
    with a long password told an attacker whether an address had an account.
    """
    make_user(session, "exists@example.com")

    existing = client.post(
        "/auth/login", json={"email": "exists@example.com", "password": OVER_LIMIT}
    )
    missing = client.post(
        "/auth/login", json={"email": "absent@example.com", "password": OVER_LIMIT}
    )

    assert existing.status_code == missing.status_code == 401
    assert existing.json() == missing.json()


# ---------------------------------------------------------------------------
# The fields that *set* a password reject it up front
# ---------------------------------------------------------------------------


def test_creating_a_user_with_an_over_long_password_is_422(client, session):
    """422 naming the field, not a 500 from inside the hashing call."""
    create_user_and_login(client, session, "admin@example.com", Role.ADMIN)

    response = client.post(
        "/users/",
        json={
            "email": "new@example.com",
            "full_name": "New",
            "temporary_password": OVER_LIMIT,
            "role": "attorney",
        },
    )

    assert response.status_code == 422


def test_changing_to_an_over_long_password_is_422(client, session):
    create_user_and_login(client, session, "admin@example.com", Role.ADMIN)

    response = client.post(
        "/auth/change-password",
        json={"current_password": "password123", "new_password": OVER_LIMIT},
    )

    assert response.status_code == 422


def test_a_password_at_the_limit_is_accepted_end_to_end(client, session):
    """The limit must not be off by one in the direction that locks people out."""
    create_user_and_login(client, session, "admin@example.com", Role.ADMIN)

    response = client.post(
        "/users/",
        json={
            "email": "boundary@example.com",
            "full_name": "Boundary",
            "temporary_password": AT_LIMIT,
            "role": "attorney",
        },
    )

    assert response.status_code == 201


@pytest.mark.parametrize(
    ("password", "expected"),
    [
        ("كلمة" * 20 + "1", 422),  # 40 Arabic chars, 80+ bytes -- over the limit
        ("كلمةسر123", 201),  # short Arabic password, comfortably under
    ],
)
def test_the_limit_counts_bytes_not_characters(client, session, password, expected):
    """bcrypt counts encoded length. Arabic is ~2 bytes per character, so a
    password well under 72 *characters* can be over 72 *bytes* — and this
    project's users write Arabic. Counting characters would let exactly those
    passwords through to the crash this test exists to prevent.
    """
    create_user_and_login(client, session, "admin@example.com", Role.ADMIN)

    response = client.post(
        "/users/",
        json={
            "email": "arabic@example.com",
            "full_name": "Arabic",
            "temporary_password": password,
            "role": "attorney",
        },
    )

    assert response.status_code == expected
