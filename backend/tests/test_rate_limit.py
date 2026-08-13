"""Login rate limiting: two buckets, a forgeable header, and a growing table.

The per-IP bucket used to be the only one, which was measurably wrong inside
compose: a request from the host arrives as the Docker bridge gateway, so every
client outside the container shares one address and the limit applied to all of
them at once. Six attempts naming six different accounts, and the sixth was
refused. The per-email bucket is the one that survives that.
"""

from datetime import UTC, datetime, timedelta

from foundation import rate_limit
from foundation.hashing import hash_password
from foundation.models import Role, User
from foundation.rate_limit import (
    MAX_ATTEMPTS_PER_EMAIL,
    MAX_ATTEMPTS_PER_IP,
    MAX_PASSWORD_CHANGES_PER_USER,
    RATE_LIMIT_WINDOW,
    client_ip,
)
from tests.conftest import create_user_and_login


class FakeRequest:
    """Just the one thing `client_ip` reads."""

    def __init__(self, peer: str):
        self.client = type("Client", (), {"host": peer})()


def make_user(session, email: str) -> User:
    user = User(
        email=email,
        full_name="Rate Limited",
        hashed_password=hash_password("password123"),
        role=Role.ADMIN,
        must_change_password=False,
    )
    session.add(user)
    session.commit()
    return user


def attempt(client, email: str, password: str = "wrongpassword1") -> int:
    response = client.post("/auth/login", json={"email": email, "password": password})
    return response.status_code


# ---------------------------------------------------------------------------
# client_ip
# ---------------------------------------------------------------------------


def test_the_socket_address_is_used():
    assert client_ip(FakeRequest("203.0.113.9")) == "203.0.113.9"


def test_a_request_with_no_client_is_not_a_crash():
    request = FakeRequest("unused")
    request.client = None

    assert client_ip(request) == "unknown"


# ---------------------------------------------------------------------------
# The per-email bucket
# ---------------------------------------------------------------------------


def test_repeated_attempts_on_one_account_are_stopped(client, session):
    make_user(session, "target@example.com")

    codes = [attempt(client, "target@example.com") for _ in range(MAX_ATTEMPTS_PER_EMAIL + 1)]

    assert codes[:MAX_ATTEMPTS_PER_EMAIL] == [401] * MAX_ATTEMPTS_PER_EMAIL
    assert codes[-1] == 429


def test_the_account_limit_is_not_case_sensitive(client, session):
    """Otherwise alternating capitalisation buys five more attempts per
    spelling, and an email address is case-insensitive in practice anyway."""
    make_user(session, "target@example.com")

    for _ in range(MAX_ATTEMPTS_PER_EMAIL):
        attempt(client, "target@example.com")

    assert attempt(client, "TARGET@Example.COM") == 429


def test_one_account_being_limited_does_not_lock_out_another(client, session):
    """The bucket must be per account, not global. A shared limit would let
    anyone deny logins to everyone by hammering a single address."""
    make_user(session, "target@example.com")
    make_user(session, "bystander@example.com")

    for _ in range(MAX_ATTEMPTS_PER_EMAIL + 1):
        attempt(client, "target@example.com")

    assert attempt(client, "bystander@example.com", "password123") == 200


def test_an_unknown_account_is_limited_too(client, session):
    """Guessing addresses must cost the same as guessing passwords, or the
    limiter becomes a way to enumerate which accounts exist."""
    codes = [attempt(client, "nobody@example.com") for _ in range(MAX_ATTEMPTS_PER_EMAIL + 1)]

    assert codes[-1] == 429


# ---------------------------------------------------------------------------
# The per-IP bucket
# ---------------------------------------------------------------------------


def test_the_address_limit_is_loose_enough_for_a_shared_one(client, session):
    """The regression that started this. Inside compose every external client
    shares the bridge gateway address, so a room of people signing in must not
    exhaust one bucket. Six accounts, one address, all served.
    """
    for index in range(6):
        make_user(session, f"person{index}@example.com")

    codes = [attempt(client, f"person{index}@example.com", "password123") for index in range(6)]

    assert codes == [200] * 6


def test_the_address_limit_still_bounds_a_flood(client, session):
    """Loose is not absent. Distinct accounts from one address, past the
    per-address limit, are still refused."""
    codes = [
        attempt(client, f"flood{index}@example.com") for index in range(MAX_ATTEMPTS_PER_IP + 1)
    ]

    assert codes[-1] == 429


# ---------------------------------------------------------------------------
# The table itself
# ---------------------------------------------------------------------------


def test_a_rejected_attempt_is_not_recorded():
    """Otherwise a client that keeps hammering holds its own window open and
    the limit never lifts — that punishes persistence rather than rate."""
    now = datetime.now(UTC)
    key = "email:someone@example.com"

    for _ in range(MAX_ATTEMPTS_PER_EMAIL):
        assert rate_limit._register(key, MAX_ATTEMPTS_PER_EMAIL, now) is False

    assert rate_limit._register(key, MAX_ATTEMPTS_PER_EMAIL, now) is True
    assert len(rate_limit._attempts[key]) == MAX_ATTEMPTS_PER_EMAIL


def test_the_window_lifts_the_limit():
    now = datetime.now(UTC)
    key = "email:someone@example.com"

    for _ in range(MAX_ATTEMPTS_PER_EMAIL):
        rate_limit._register(key, MAX_ATTEMPTS_PER_EMAIL, now)
    assert rate_limit._register(key, MAX_ATTEMPTS_PER_EMAIL, now) is True

    later = now + RATE_LIMIT_WINDOW + timedelta(seconds=1)
    assert rate_limit._register(key, MAX_ATTEMPTS_PER_EMAIL, later) is False


def test_stale_keys_are_forgotten_once_the_table_grows():
    """The table is keyed on attacker-supplied values, so it must not grow
    without bound. Before this, a key was created per address and per account
    and never removed — a slow leak in a process meant to run for weeks.
    """
    old = datetime.now(UTC) - RATE_LIMIT_WINDOW - timedelta(minutes=5)
    for index in range(rate_limit._FORGET_ABOVE_KEYS + 1):
        rate_limit._attempts[f"ip:198.51.100.{index}"] = [old]

    rate_limit._register("email:live@example.com", MAX_ATTEMPTS_PER_EMAIL, datetime.now(UTC))

    assert len(rate_limit._attempts) == 1
    assert "email:live@example.com" in rate_limit._attempts


# ---------------------------------------------------------------------------
# Change-password: the other door with a password behind it.
#
# Login has been counted since LEG-22, which meant guessing was throttled at the
# front and unthrottled at this one -- reachable by anyone holding a session,
# and a hit takes the account outright.
# ---------------------------------------------------------------------------


def change_password(client, current: str = "wrongpassword1"):
    return client.post(
        "/auth/change-password",
        json={"current_password": current, "new_password": "newpassword123"},
    )


def test_password_change_guesses_are_capped(client, session):
    create_user_and_login(client, session, "guessed@example.com", Role.ATTORNEY)

    for number in range(MAX_PASSWORD_CHANGES_PER_USER):
        response = change_password(client)
        print(f"Guess {number + 1} -> {response.status_code}")
        assert response.status_code == 401

    blocked = change_password(client)
    print(f"Guess {MAX_PASSWORD_CHANGES_PER_USER + 1} -> {blocked.status_code} {blocked.json()}")
    assert blocked.status_code == 429


def test_the_cap_does_not_reach_across_accounts(client, session):
    create_user_and_login(client, session, "victim@example.com", Role.ATTORNEY)
    for _ in range(MAX_PASSWORD_CHANGES_PER_USER):
        change_password(client)
    assert change_password(client).status_code == 429

    create_user_and_login(client, session, "unrelated@example.com", Role.ATTORNEY)

    theirs = change_password(client, current="password123")
    print(f"an unrelated account's first, correct attempt -> {theirs.status_code}")
    assert theirs.status_code == 200


def test_a_busy_key_survives_the_sweep():
    """Sweeping must drop what is stale, not what is merely numerous."""
    now = datetime.now(UTC)
    old = now - RATE_LIMIT_WINDOW - timedelta(minutes=5)
    for index in range(rate_limit._FORGET_ABOVE_KEYS + 1):
        rate_limit._attempts[f"ip:198.51.100.{index}"] = [old]
    rate_limit._attempts["ip:203.0.113.9"] = [now]

    rate_limit._register("email:live@example.com", MAX_ATTEMPTS_PER_EMAIL, now)

    assert "ip:203.0.113.9" in rate_limit._attempts
