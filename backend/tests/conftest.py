import os
from pathlib import Path

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from foundation.database import get_session
from foundation.hashing import hash_password
from foundation.models import User
from main import app

# Force tests onto their own throwaway database, regardless of what the
# app's own .env points at (that one must stay pointed at the real dev
# database). override=True means this always wins over anything already
# loaded — including a plain DATABASE_URL from .env or the shell.
# In CI, .env.test isn't present, so this is a no-op and CI's own
# DATABASE_URL (set directly in the workflow) is used instead.
#
# The path is absolute on purpose. A relative ".env.test" silently finds
# nothing when pytest is launched from the repo root instead of backend/, and
# DATABASE_URL then falls through to whatever else is set — which was the DEV
# database. The engine fixture below calls drop_all(), so that run destroyed
# the dev schema and still reported 176 tests passing.
load_dotenv(Path(__file__).parent.parent / ".env.test", override=True)

# Second line of defence: the path fix above stops one cause, but this still
# trusts whatever DATABASE_URL ends up saying. Since the engine fixture calls
# drop_all(), pointing it at a real database destroys that database and reports
# success — a failure with no signal at all. CI uses legalmind_test, so this
# holds there too.
_database_url = os.environ.get("DATABASE_URL", "")
if not _database_url.endswith("_test"):
    raise RuntimeError(
        f"Refusing to run tests against {_database_url!r} — the engine fixture "
        "calls drop_all() and would destroy it. DATABASE_URL must name a "
        "database ending in _test."
    )


@pytest.fixture(scope="session")
def engine():
    test_engine = create_engine(os.environ["DATABASE_URL"])
    # pgvector has to exist before create_all, because DocumentChunk declares a
    # Vector column. Tests build the schema straight from the models rather than
    # running migrations, so the CREATE EXTENSION inside LEG-58's migration never
    # executes here — without this line every test fails with
    # 'type "vector" does not exist'.
    with test_engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
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


@pytest.fixture(autouse=True)
def reset_rate_limits():
    from foundation.rate_limit import _login_attempts

    _login_attempts.clear()
    yield


@pytest.fixture
def minimal_pdf_bytes() -> bytes:
    """The smallest PDF pypdf can parse without erroring — one blank page."""
    return (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]"
        b"/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
        b"4 0 obj<</Length 44>>stream\n"
        b"BT /F1 12 Tf 20 100 Td (Hello world) Tj ET\n"
        b"endstream endobj\n"
        b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
        b"xref\n0 6\n0000000000 65535 f \n"
        b"trailer<</Size 6/Root 1 0 R>>\n"
        b"startxref\n0\n%%EOF"
    )


def create_user_and_login(
    client,
    session,
    email: str,
    role: str,
    password: str = "password123",
    must_change_password: bool = False,
) -> int:
    """Create a user directly in the DB (no register endpoint), then log them in."""
    user = User(
        email=email,
        full_name="Test User",
        hashed_password=hash_password(password),
        role=role,
        must_change_password=must_change_password,
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    client.post("/auth/login", json={"email": email, "password": password})
    return user.id
