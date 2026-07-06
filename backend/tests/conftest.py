import os

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from foundation.database import get_session
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
