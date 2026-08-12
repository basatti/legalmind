"""The expired-session sweep, and the schedule that decides when it runs.

Expiry was enforced only on read: a session is deleted when someone presents an
expired one. A user who logs in and never comes back leaves a row nothing ever
visits again, so the table only grew. This is the other half.

The boundary cases here are deliberately narrow — one minute either side of the
cutoff. `expires_at` is a naive `timestamp` column written from an aware UTC
datetime, so a timezone mismatch between what is stored and what the sweep
compares against would shift the cutoff by hours. Wide margins would not notice.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import select

from foundation.hashing import hash_password
from foundation.models import Role, User
from foundation.models import Session as SessionModel
from foundation.settings import (
    DEFAULT_SESSION_REAP_INTERVAL_MINUTES,
    resolve_reap_interval_minutes,
)
from repositories.session_repository import SessionRepository
from worker_main import SESSION_REAP_INTERVAL, reap_due, reap_expired_sessions


def make_user(session, email: str = "reaper@example.com") -> User:
    user = User(
        email=email,
        full_name="Reaper User",
        hashed_password=hash_password("password123"),
        role=Role.ADMIN,
        must_change_password=False,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def make_session(db, user_id: int, expires_at: datetime) -> str:
    session_id = str(uuid.uuid4())
    db.add(SessionModel(id=session_id, user_id=user_id, expires_at=expires_at))
    db.commit()
    return session_id


# ---------------------------------------------------------------------------
# delete_expired
# ---------------------------------------------------------------------------


def test_expired_sessions_are_deleted_and_live_ones_are_not(session):
    user = make_user(session)
    now = datetime.now(UTC)
    dead = make_session(session, user.id, now - timedelta(hours=2))
    alive = make_session(session, user.id, now + timedelta(hours=2))

    deleted = SessionRepository(session).delete_expired(now)

    assert deleted == 1
    assert SessionRepository(session).get_by_id(dead) is None
    assert SessionRepository(session).get_by_id(alive) is not None


def test_the_cutoff_is_not_shifted_by_a_timezone(session):
    """One minute either side — a stored/compared timezone mismatch would move
    the cutoff by whole hours and take the wrong row."""
    user = make_user(session)
    now = datetime.now(UTC)
    just_expired = make_session(session, user.id, now - timedelta(minutes=1))
    expiring_shortly = make_session(session, user.id, now + timedelta(minutes=1))

    deleted = SessionRepository(session).delete_expired(now)

    assert deleted == 1
    assert SessionRepository(session).get_by_id(just_expired) is None
    assert SessionRepository(session).get_by_id(expiring_shortly) is not None


def test_a_session_expiring_exactly_now_survives(session):
    """`< now`, not `<= now`. A session is valid up to its expiry instant, and
    `AuthService` agrees — it rejects only when `now > expires_at`."""
    user = make_user(session)
    now = datetime.now(UTC)
    borderline = make_session(session, user.id, now)

    deleted = SessionRepository(session).delete_expired(now)

    assert deleted == 0
    assert SessionRepository(session).get_by_id(borderline) is not None


def test_sweeping_an_empty_table_reports_nothing(session):
    assert SessionRepository(session).delete_expired(datetime.now(UTC)) == 0


def test_a_reaped_session_no_longer_authenticates(client, session):
    """Ties the sweep to the thing it is sweeping.

    The repository deleting rows proves nothing on its own unless those rows
    are the ones authentication reads. Log in for real, expire the session by
    moving its `expires_at` into the past, sweep, and the cookie the client is
    still holding must stop working.
    """
    make_user(session)
    client.post("/auth/login", json={"email": "reaper@example.com", "password": "password123"})
    assert client.get("/users/").status_code == 200

    live = session.exec(select(SessionModel)).one()
    live.expires_at = datetime.now(UTC) - timedelta(hours=1)
    session.add(live)
    session.commit()

    assert SessionRepository(session).delete_expired(datetime.now(UTC)) == 1
    assert client.get("/users/").status_code == 401


# ---------------------------------------------------------------------------
# reap_due — the schedule
# ---------------------------------------------------------------------------


INTERVAL = timedelta(minutes=60)


def test_a_process_that_has_never_swept_is_due():
    """Otherwise a worker restarted more often than the interval would never
    reach it, and would never sweep at all."""
    assert reap_due(datetime.now(UTC), None, INTERVAL) is True


def test_not_due_before_the_interval_has_passed():
    now = datetime.now(UTC)
    assert reap_due(now, now - timedelta(minutes=59), INTERVAL) is False


def test_due_once_the_interval_has_passed():
    now = datetime.now(UTC)
    assert reap_due(now, now - timedelta(minutes=61), INTERVAL) is True


def test_due_exactly_on_the_interval():
    now = datetime.now(UTC)
    assert reap_due(now, now - INTERVAL, INTERVAL) is True


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------


class BrokenSession:
    """Stands in for a database session that has gone bad mid-sweep."""

    def exec(self, *args: object, **kwargs: object) -> object:
        raise RuntimeError("connection is gone")


def test_a_failed_sweep_does_not_stop_the_worker(caplog):
    """The queue matters more than the sweep.

    A document that never becomes searchable is a user-visible failure; a
    session row surviving an extra hour is not. If this raised, one bad sweep
    would take ingestion down with it.
    """
    reap_expired_sessions(BrokenSession(), datetime.now(UTC))  # type: ignore[arg-type]

    assert "expired-session sweep failed" in caplog.text


def test_a_successful_sweep_of_nothing_stays_quiet(session, caplog):
    """No log line when there was nothing to delete — an hourly 'deleted 0
    sessions' is noise that trains people to ignore the log."""
    reap_expired_sessions(session, datetime.now(UTC))

    assert "expired session" not in caplog.text


def test_a_sweep_that_deletes_something_says_so(session, caplog):
    import logging

    caplog.set_level(logging.INFO)
    user = make_user(session)
    make_session(session, user.id, datetime.now(UTC) - timedelta(hours=2))

    reap_expired_sessions(session, datetime.now(UTC))

    assert "deleted 1 expired session(s)" in caplog.text


# ---------------------------------------------------------------------------
# The interval setting
# ---------------------------------------------------------------------------


def test_the_worker_interval_comes_from_settings():
    """Pins the wiring, not the value — the constant the loop uses must be the
    one the settings module resolved, or the environment variable is decorative.
    """
    from foundation import settings

    assert timedelta(minutes=settings.SESSION_REAP_INTERVAL_MINUTES) == SESSION_REAP_INTERVAL


@pytest.mark.parametrize("raw", ["", "   "])
def test_an_unset_interval_uses_the_default(raw):
    assert resolve_reap_interval_minutes(raw) == DEFAULT_SESSION_REAP_INTERVAL_MINUTES


def test_a_valid_interval_is_used():
    assert resolve_reap_interval_minutes(" 15 ") == 15


@pytest.mark.parametrize("raw", ["hourly", "1.5", "60m"])
def test_a_non_numeric_interval_is_refused(raw):
    """A misread interval is invisible: the worker keeps draining the queue and
    simply never reaps, which is the bug this whole change exists to fix."""
    with pytest.raises(RuntimeError) as exc:
        resolve_reap_interval_minutes(raw)

    assert raw in str(exc.value)


@pytest.mark.parametrize("raw", ["0", "-5"])
def test_a_non_positive_interval_is_refused(raw):
    with pytest.raises(RuntimeError):
        resolve_reap_interval_minutes(raw)
