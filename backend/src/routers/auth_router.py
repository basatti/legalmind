"""Authentication endpoints."""

from fastapi import APIRouter, Cookie, Depends, Response, status
from sqlmodel import Session

from foundation.database import get_session
from foundation.models import User
from foundation.schemas import (
    LoginRequest,
    MessageResponse,
    UserRegisterRequest,
    UserResponse,
)
from repositories.session_repository import SessionRepository
from repositories.user_repository import UserRepository
from services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])

# Cookie name — one constant, referenced in login, logout, and current_user
SESSION_COOKIE_NAME = "session_id"


# ---------------------------------------------------------------------------
# Dependency — builds AuthService with both repositories
# ---------------------------------------------------------------------------


def get_auth_service(session: Session = Depends(get_session)) -> AuthService:
    return AuthService(
        user_repository=UserRepository(session),
        session_repository=SessionRepository(session),
    )


# ---------------------------------------------------------------------------
# POST /auth/register  (LEG-21, unchanged)
# ---------------------------------------------------------------------------


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    data: UserRegisterRequest,
    service: AuthService = Depends(get_auth_service),
) -> User:
    return service.register(data)


# ---------------------------------------------------------------------------
# POST /auth/login  (LEG-22)
# ---------------------------------------------------------------------------


@router.post("/login", response_model=MessageResponse)
def login(
    data: LoginRequest,
    response: Response,
    service: AuthService = Depends(get_auth_service),
) -> MessageResponse:
    """Verify credentials, create server-side session, set httpOnly cookie."""
    session_id = service.login(data)

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,  # not accessible via JS — prevents XSS theft
        samesite="lax",  # CSRF protection for browser requests
        secure=False,  # set True in production (HTTPS only)
        max_age=60 * 60 * 24,  # 24 hours, matches SESSION_TTL_HOURS
    )

    return MessageResponse(message="Logged in successfully")


# ---------------------------------------------------------------------------
# POST /auth/logout  (LEG-22)
# ---------------------------------------------------------------------------


@router.post("/logout", response_model=MessageResponse)
def logout(
    response: Response,
    service: AuthService = Depends(get_auth_service),
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> MessageResponse:
    """Invalidate the session and clear the cookie."""
    if session_id:
        service.logout(session_id)

    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        httponly=True,
        samesite="lax",
    )

    return MessageResponse(message="Logged out successfully")
