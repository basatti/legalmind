"""Simple in-memory rate limiting for login attempts."""

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request, status

RATE_LIMIT_WINDOW = timedelta(minutes=1)
MAX_ATTEMPTS_PER_WINDOW = 5

# Maps IP address -> list of timestamps of recent login attempts.
# In-memory only: resets on server restart, and only works correctly
# with a single backend process.
_login_attempts: dict[str, list[datetime]] = defaultdict(list)


def check_login_rate_limit(request: Request) -> None:
    """Raise HTTP 429 if this IP has made too many login attempts recently."""
    ip = request.client.host if request.client else "unknown"
    now = datetime.now(UTC)

    recent_attempts = [
        timestamp for timestamp in _login_attempts[ip] if now - timestamp < RATE_LIMIT_WINDOW
    ]

    if len(recent_attempts) >= MAX_ATTEMPTS_PER_WINDOW:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again later.",
        )

    recent_attempts.append(now)
    _login_attempts[ip] = recent_attempts
