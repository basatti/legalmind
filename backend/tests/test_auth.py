from datetime import UTC, datetime, timedelta

from foundation.models import Role, User
from foundation.models import Session as SessionModel
from tests.conftest import create_user_and_login


def test_valid_login(client, session):
    create_user_and_login(client, session, "alice@example.com", Role.ATTORNEY)

    response = client.post(
        "/auth/login",
        json={
            "email": "alice@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 200
    assert "session_id" in response.cookies


def test_wrong_password(client, session):
    create_user_and_login(client, session, "bob@example.com", Role.ATTORNEY)

    response = client.post(
        "/auth/login",
        json={
            "email": "bob@example.com",
            "password": "wrongpassword1",
        },
    )
    assert response.status_code == 401


def test_invalid_or_expired_session(client, session):
    # A session ID that was never created
    response = client.get("/auth/me", cookies={"session_id": "does-not-exist"})
    assert response.status_code == 401

    # A session that exists, but already expired
    user = User(
        email="charlie@example.com",
        full_name="Charlie",
        hashed_password="irrelevant-for-this-test",
        role=Role.ATTORNEY,
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    expired_session = SessionModel(
        id="expired-session-id",
        user_id=user.id,
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )
    session.add(expired_session)
    session.commit()

    response = client.get("/auth/me", cookies={"session_id": "expired-session-id"})
    assert response.status_code == 401


def test_protected_route_requires_login(client):
    response = client.get("/cases/")
    assert response.status_code == 401


def test_forced_password_change_gate(client, session):
    """LEG-55: temp login -> blocked -> change -> unblocked."""
    create_user_and_login(
        client,
        session,
        "temp@example.com",
        Role.ATTORNEY,
        password="temporary123",
        must_change_password=True,
    )

    # Blocked from a normal route while must_change_password is True
    blocked = client.get("/cases/")
    print(f"GET /cases/ while must_change_password=True -> {blocked.status_code} {blocked.json()}")
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "Password change required"

    # But /auth/me stays reachable, and correctly reports the flag
    me = client.get("/auth/me")
    me_data = me.json()
    print(f"GET /auth/me -> {me.status_code} flag={me_data['must_change_password']}")
    assert me.status_code == 200
    assert me_data["must_change_password"] is True

    # Change the password
    changed = client.post(
        "/auth/change-password",
        json={"current_password": "temporary123", "new_password": "newpassword123"},
    )
    print(f"POST /auth/change-password -> {changed.status_code}")
    assert changed.status_code == 200

    # Now unblocked
    unblocked = client.get("/cases/")
    print(f"GET /cases/ after password change -> {unblocked.status_code}")
    assert unblocked.status_code == 200


def test_temp_password_user_can_still_logout(client, session):
    """A temp-password user must be able to log out, not just change password."""
    create_user_and_login(
        client,
        session,
        "temp2@example.com",
        Role.ATTORNEY,
        password="temporary123",
        must_change_password=True,
    )

    response = client.post("/auth/logout")
    print(f"POST /auth/logout while must_change_password=True -> {response.status_code}")
    assert response.status_code == 200


def test_switched_off_account_loses_a_live_session(client, session):
    """The bug this test exists for: an account switched off mid-session kept working.

    `login` checked `is_active` and nothing after it did, so the check only ever
    ran on the way in. Anyone already holding a session carried on reading cases
    and asking questions until the 24-hour expiry.
    """
    user_id = create_user_and_login(client, session, "leaver@example.com", Role.ATTORNEY)

    # The session works while the account is on.
    assert client.get("/auth/me").status_code == 200

    # Switch the account off, which today means editing the row by hand --
    # there is no endpoint for it yet. That is exactly why nobody noticed.
    user = session.get(User, user_id)
    user.is_active = False
    session.add(user)
    session.commit()

    # Same client, same cookie, nothing re-sent -- and now refused.
    blocked = client.get("/auth/me")
    print(f"GET /auth/me after switching the account off -> {blocked.status_code}")
    assert blocked.status_code == 401

    # Not just /auth/me. A route carrying real case data is the one that matters.
    cases = client.get("/cases/")
    print(f"GET /cases/ after switching the account off -> {cases.status_code}")
    assert cases.status_code == 401


def test_rejected_session_row_is_deleted(client, session):
    """Rejecting the session also removes it, like the expired branch does."""
    user_id = create_user_and_login(client, session, "leaver2@example.com", Role.ATTORNEY)
    session_id = client.cookies["session_id"]

    assert session.get(SessionModel, session_id) is not None

    user = session.get(User, user_id)
    user.is_active = False
    session.add(user)
    session.commit()

    client.get("/auth/me")

    # The row can never be used again, so it does not wait for the reaper.
    session.expire_all()
    assert session.get(SessionModel, session_id) is None


def test_switched_off_account_cannot_log_in_again(client, session):
    """The other half of the story, and why the two return different codes.

    Logging in is a request to be let in, and gets told why it was refused.
    Presenting a dead session is not, and gets the same 401 as any other
    credential that no longer identifies anybody.
    """
    user_id = create_user_and_login(client, session, "leaver3@example.com", Role.ATTORNEY)

    user = session.get(User, user_id)
    user.is_active = False
    session.add(user)
    session.commit()

    response = client.post(
        "/auth/login",
        json={"email": "leaver3@example.com", "password": "password123"},
    )
    print(f"POST /auth/login for a switched-off account -> {response.status_code}")
    assert response.status_code == 403
    assert response.json()["detail"] == "Account is inactive"


def test_login_rate_limit(client, session):
    create_user_and_login(client, session, "ratelimit@example.com", Role.ATTORNEY)
    # create_user_and_login already used 1 login attempt, so 4 more fit under the limit
    for i in range(4):
        response = client.post(
            "/auth/login",
            json={"email": "ratelimit@example.com", "password": "password123"},
        )
        print(f"Attempt {i + 2} -> {response.status_code}")
        assert response.status_code == 200

    # The 6th attempt overall should be blocked
    blocked = client.post(
        "/auth/login",
        json={"email": "ratelimit@example.com", "password": "password123"},
    )
    print(f"Attempt 6 (should be blocked) -> {blocked.status_code} {blocked.json()}")
    assert blocked.status_code == 429
