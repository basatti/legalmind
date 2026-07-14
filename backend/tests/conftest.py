import os

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from foundation.database import get_session
from main import app

# Force tests onto their own throwaway database, regardless of what the
# app's own .env points at (that one must stay pointed at the real dev
# database). override=True means this always wins over anything already
# loaded — including a plain DATABASE_URL from .env or the shell.
# In CI, .env.test isn't present, so this is a no-op and CI's own
# DATABASE_URL (set directly in the workflow) is used instead.
load_dotenv(".env.test", override=True)


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
