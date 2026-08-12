"""Environment settings and the session cookie they shape.

Two things are worth pinning here. The first is that a misspelled ENVIRONMENT
fails loudly instead of resolving to the opposite of what its author meant. The
second is that the cookie's Max-Age is *derived* from SESSION_TTL_HOURS rather
than restated — that one used to be a literal `60 * 60 * 24` sitting next to a
comment claiming it matched, which is exactly the kind of agreement that holds
until someone edits one side.
"""

import pytest

from foundation import settings
from foundation.hashing import hash_password
from foundation.models import Role, User
from foundation.settings import (
    DEVELOPMENT,
    PRODUCTION,
    resolve_environment,
)
from services.auth_service import SESSION_TTL_HOURS


def make_user(session, email: str = "cookie@example.com") -> User:
    user = User(
        email=email,
        full_name="Cookie User",
        hashed_password=hash_password("password123"),
        role=Role.ADMIN,
        must_change_password=False,
    )
    session.add(user)
    session.commit()
    return user


def login(client, email: str = "cookie@example.com"):
    return client.post("/auth/login", json={"email": email, "password": "password123"})


# ---------------------------------------------------------------------------
# resolve_environment
# ---------------------------------------------------------------------------


def test_unset_resolves_to_development():
    """Absence is a decision this project made and wrote down, not an error."""
    assert resolve_environment("") == DEVELOPMENT


def test_whitespace_only_resolves_to_development():
    assert resolve_environment("   ") == DEVELOPMENT


def test_case_and_padding_are_normalised():
    assert resolve_environment("  PRODUCTION  ") == PRODUCTION


def test_an_unknown_environment_is_refused():
    """A typo is not a decision, so it must not resolve to anything.

    Silently falling back to the default here would mean someone who wrote
    ENVIRONMENT=prod got development — the opposite of their intent, with no
    signal until something behaves oddly much later.
    """
    with pytest.raises(RuntimeError) as exc:
        resolve_environment("prod")

    # The offending value belongs in the message; a guard that hides what it
    # rejected sends the reader back to guessing.
    assert "prod" in str(exc.value)


def test_the_refusal_names_the_allowed_values():
    with pytest.raises(RuntimeError) as exc:
        resolve_environment("staging")

    message = str(exc.value)
    assert DEVELOPMENT in message
    assert PRODUCTION in message


# ---------------------------------------------------------------------------
# The derived cookie flag
# ---------------------------------------------------------------------------


def test_tests_run_as_development_with_an_insecure_cookie():
    """Pins the local default rather than assuming it.

    If this fails, ENVIRONMENT is set in the environment running the suite —
    which would silently change what every cookie assertion below is testing.
    """
    assert settings.ENVIRONMENT == DEVELOPMENT
    assert settings.COOKIE_SECURE is False


# ---------------------------------------------------------------------------
# The cookie itself
# ---------------------------------------------------------------------------


def test_login_cookie_is_not_secure_locally(client, session):
    make_user(session)

    header = login(client).headers["set-cookie"]

    assert "Secure" not in header
    assert "HttpOnly" in header
    assert "SameSite=lax" in header


def test_login_cookie_max_age_tracks_the_session_ttl(client, session):
    """The whole point of the change: one fact, one source.

    Asserting the literal 86400 would re-create the duplication in the test.
    Deriving it from the same constant the router uses means changing the TTL
    keeps this test honest instead of making it a second thing to remember.
    """
    make_user(session)

    header = login(client).headers["set-cookie"]

    assert f"Max-Age={SESSION_TTL_HOURS * 60 * 60}" in header


def test_login_cookie_is_secure_when_the_setting_says_so(client, session, monkeypatch):
    """The other direction, so the flag is proven to be read rather than
    hardcoded to a new constant. The router reads it through the module, which
    is what makes patching one place sufficient."""
    monkeypatch.setattr(settings, "COOKIE_SECURE", True)
    make_user(session)

    header = login(client).headers["set-cookie"]

    assert "Secure" in header


def test_logout_cookie_matches_the_login_cookie(client, session, monkeypatch):
    """Deletion does not need Secure to match — browsers key on
    name/domain/path — but the two calls should not look different for no
    reason, and a reader comparing them should not have to work out which
    difference is meaningful."""
    monkeypatch.setattr(settings, "COOKIE_SECURE", True)
    make_user(session)
    login(client)

    header = client.post("/auth/logout").headers["set-cookie"]

    assert "Secure" in header
