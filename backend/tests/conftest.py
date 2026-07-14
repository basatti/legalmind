import os

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from foundation.database import get_session
from foundation.hashing import hash_password
from foundation.models import User
from main import app


@pytest.fixture(scope="session")
def engine():
    test_engine = create_engine(os.environ["DATABASE_URL"])
    SQLModel.metadata.create_all(test_engine)
    yield test_engine
    SQLModel.metadata.drop_all(test_engine)


@pytest.fixture
def session(engine):
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(session):
    def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def create_user_and_login(
    client, session, email: str, role: str, password: str = "password123"
) -> int:
    """Create a user directly in the DB (no register endpoint), then log them in."""
    user = User(
        email=email,
        full_name="Test User",
        hashed_password=hash_password(password),
        role=role,
        must_change_password=False,
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    client.post("/auth/login", json={"email": email, "password": password})
    return user.id
