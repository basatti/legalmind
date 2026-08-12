"""Rate limiting for login attempts.

Two buckets, deliberately asymmetric, because they defend different things and
only one of them can be trusted to identify anybody.

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

_FORGET_ABOVE_KEYS = 1024
"""Sweep stale keys once the table grows past this.

The table is keyed on attacker-supplied values, so it must not grow without
bound; sweeping on every request instead would be O(keys) per login for no
benefit at the sizes anyone here will ever see.
"""

# key -> timestamps of recent attempts. Keys are namespaced ("ip:" / "email:")
# so an address can never collide with an account name.
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


def _too_many() -> HTTPException:
    """One message for both buckets.

    Saying which limit was hit would tell an attacker whether the account they
    named is the one drawing attention, which is the same reasoning that makes
    a wrong email and a wrong password return an identical 401.
    """
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many login attempts. Please try again later.",
    )


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
