from datetime import UTC, datetime, timedelta

from foundation.models import Role, User
from foundation.models import Session as SessionModel


def test_valid_login(client):
    client.post(
        "/auth/register",
        json={
            "email": "alice@example.com",
            "full_name": "Alice",
            "password": "password123",
        },
    )

    response = client.post(
        "/auth/login",
        json={
            "email": "alice@example.com",
            "password": "password123",
        },
    )

    assert response.status_code == 200
    assert "session_id" in response.cookies


def test_wrong_password(client):
    client.post(
        "/auth/register",
        json={
            "email": "bob@example.com",
            "full_name": "Bob",
            "password": "correctpassword1",
        },
    )

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
