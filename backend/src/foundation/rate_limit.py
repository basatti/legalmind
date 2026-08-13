"""Rate limiting for the endpoints where an unbounded number of calls costs something.

Three activities are counted, and they are counted against different things
because only some callers can be identified.

The two login buckets came first and are the awkward ones, since a request
arriving at the login page has not proved who it is yet. The two later buckets
guard endpoints that run *after* authentication, so they can key on the user id
and simply be right about who is calling -- see "Per user" at the end.

**Per email — the tight one.** Many attempts naming one account is password
guessing, and the account name is stated in the request, so this works no
matter what the network does to the source address. Five per minute.

**Per IP — the loose one.** Many attempts from one source across many accounts
is credential stuffing. The catch is that "one source" is a guess: an address
can be a person, an office, or an entire NAT'd network, and this project has a
worked example. Inside `docker compose`, a request from the host machine
reaches the API as `172.18.0.1`, the bridge gateway — *every* client outside the
container shares that one address. Measured, not assumed: six login attempts
from the host naming six different accounts, and the sixth was rejected.

So the per-IP limit is set where it cannot punish a shared address during
ordinary use, while still bounding a flood. It is not the real protection any
more, and pretending otherwise would be the mistake.

Note that `X-Forwarded-For` would not rescue this and is deliberately not read:
NAT rewrites the source address without adding a header, so there is nothing to
recover. Believing that header without a proxy in front would be strictly worse
than the socket address, since any client can set it and rotate past a per-IP
limit at will.

**Per user — the two that know exactly who they are talking to.** Both guard
authenticated endpoints, so the caller has already been resolved to a row in
the user table and the identity problem above simply does not arise.

- *Password changes.* `/auth/change-password` takes the current password, and
  before this nothing counted the guesses. Anyone holding a borrowed session
  could run a common-password list against it at whatever rate the network
  allowed, and a hit takes the account outright. Login has been counted since
  LEG-22; this is the same activity -- proving you know a password -- reached
  through a different door, so it gets the same allowance.

- *Questions.* `/query/ask` is the only endpoint in this application that costs
  real money to serve: one embedding call plus one or more model calls to the
  company gateway, on hardware other teams share. Every other route reads rows
  and returns them. The realistic threat is not malice but a frontend retry
  loop, which can call it thousands of times a minute while nobody is watching
  -- so the limit is set far above what a person reading answers could ever
  reach, where hitting it means something is broken rather than someone is
  impatient.
"""

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request, status

RATE_LIMIT_WINDOW = timedelta(minutes=1)

MAX_ATTEMPTS_PER_EMAIL = 5
"""Attempts naming one account, per window. The meaningful limit."""

MAX_ATTEMPTS_PER_IP = 30
"""Attempts from one address, per window.

Six times the per-email limit because one address can legitimately be a whole
room of people — see the module docstring. Low enough to bound a flood, high
enough that a demo with several people signing in does not lock the room out,
which the previous value of 5 genuinely did.
"""

MAX_PASSWORD_CHANGES_PER_USER = 5
"""Change-password attempts by one account, per window.

The same number as `MAX_ATTEMPTS_PER_EMAIL` and for the same reason: both count
attempts to prove knowledge of a password, and there is no reading of "normal
use" under which a person needs a sixth try inside a minute.

Successful changes are counted too, rather than only failures. Counting only
failures would mean a caller who alternates a wrong guess with something that
succeeds never accumulates, and nobody legitimately changes their password five
times in a minute, so the simpler rule costs nothing.
"""

MAX_QUESTIONS_PER_USER = 10
"""Questions asked by one account, per window.

Deliberately generous. A lawyer asks, reads the answer, thinks, and asks again
-- two or three a minute is a hurried person, and ten is a number no one
reading answers will reach. A retry loop reaches it in well under a second.

Set so that hitting it carries information: this limit tripping means something
is wrong, not that someone is working hard.
"""

_FORGET_ABOVE_KEYS = 1024
"""Sweep stale keys once the table grows past this.

The table is keyed on attacker-supplied values, so it must not grow without
bound; sweeping on every request instead would be O(keys) per login for no
benefit at the sizes anyone here will ever see.
"""

# key -> timestamps of recent attempts. Keys are namespaced ("ip:", "email:",
# "password-change:", "ask:") so that no two buckets can ever collide -- an
# address cannot look like an account name, and a user id counted for questions
# is a different key from the same user id counted for password changes.
#
# In-memory, so it resets on restart and is per-process: with several API
# replicas the effective limit is the configured one times the replica count.
# Compose runs a single `app`, so that is accurate today and would need a
# shared store (Postgres or Redis) to stay true above one.
_attempts: dict[str, list[datetime]] = {}


def clear_rate_limits() -> None:
    """Forget every recorded attempt. For tests, which must not inherit state."""
    _attempts.clear()


def client_ip(request: Request) -> str:
    """The address to rate-limit against: the socket peer, and nothing else."""
    return request.client.host if request.client else "unknown"


def _forget_stale(now: datetime) -> None:
    """Drop keys with nothing left inside the window."""
    for key in [
        key
        for key, timestamps in _attempts.items()
        if all(now - timestamp >= RATE_LIMIT_WINDOW for timestamp in timestamps)
    ]:
        del _attempts[key]


def _register(key: str, limit: int, now: datetime) -> bool:
    """Record an attempt against `key`. True if it has gone over the limit.

    A rejected attempt is deliberately *not* recorded. Recording it would let a
    client that keeps hammering hold its own window open indefinitely, so the
    limit would never lift while the abuse continued — punishing persistence
    rather than rate.
    """
    if len(_attempts) > _FORGET_ABOVE_KEYS:
        _forget_stale(now)

    recent = [
        timestamp for timestamp in _attempts.get(key, []) if now - timestamp < RATE_LIMIT_WINDOW
    ]
    _attempts[key] = recent

    if len(recent) >= limit:
        return True

    recent.append(now)
    return False


def _rejection(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=detail)


def _too_many() -> HTTPException:
    """One message for both login buckets.

    Saying which limit was hit would tell an attacker whether the account they
    named is the one drawing attention, which is the same reasoning that makes
    a wrong email and a wrong password return an identical 401.

    The per-user buckets below say plainly what they are, because that reasoning
    does not reach them: their caller has already authenticated as the account
    in question and learns nothing from the answer that it did not supply.
    """
    return _rejection("Too many login attempts. Please try again later.")


def check_login_rate_limit(request: Request) -> None:
    """Per-address limit. A FastAPI dependency, so it runs before the handler."""
    if _register(f"ip:{client_ip(request)}", MAX_ATTEMPTS_PER_IP, datetime.now(UTC)):
        raise _too_many()


def check_login_attempts_for_email(email: str) -> None:
    """Per-account limit.

    Called from the handler rather than as a dependency because it needs the
    parsed body, and a dependency would have to read and re-buffer the request
    to get it. Lower-cased so that alternating capitalisation is not a way to
    get five more attempts per spelling.
    """
    key = f"email:{email.strip().lower()}"

    if _register(key, MAX_ATTEMPTS_PER_EMAIL, datetime.now(UTC)):
        raise _too_many()


def check_password_change_rate_limit(user_id: int) -> None:
    """Per-account limit on change-password attempts.

    Called from the handler rather than as a dependency to avoid a circular
    import: knowing the user means depending on `current_user`, which lives in
    `routers/auth_router`, which imports this module.
    """
    if _register(f"password-change:{user_id}", MAX_PASSWORD_CHANGES_PER_USER, datetime.now(UTC)):
        raise _rejection("Too many password change attempts. Please try again later.")


def check_ask_rate_limit(user_id: int) -> None:
    """Per-account limit on questions.

    Must be called before anything reaches the company gateway, which is the
    entire point -- a refusal is a lookup in a dict, while the call it prevents
    is an embedding, a model completion, and a line on someone's bill.

    Worth saying out loud that this bounds one process only, like every other
    bucket here (see `_attempts`). It is a guard against a runaway client, not a
    spend cap: with several API replicas the real ceiling is this number times
    the replica count, and a genuine budget limit belongs at the gateway, which
    is the only thing that sees every call.
    """
    if _register(f"ask:{user_id}", MAX_QUESTIONS_PER_USER, datetime.now(UTC)):
        raise _rejection("You are asking questions too quickly. Please wait a moment.")
