"""Authentication endpoints."""

from collections.abc import Callable

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlmodel import Session

from foundation.database import get_session
from foundation.models import User
from foundation.permissions import Permission, has_any_permission
from foundation.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    MessageResponse,
    UserResponse,
)
from repositories.session_repository import SessionRepository
from repositories.user_repository import UserRepository
from services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])

SESSION_COOKIE_NAME = "session_id"


# ---------------------------------------------------------------------------
# Dependency -- builds AuthService with both repositories
# ---------------------------------------------------------------------------


def get_auth_service(session: Session = Depends(get_session)) -> AuthService:
    return AuthService(
        user_repository=UserRepository(session),
        session_repository=SessionRepository(session),
    )


# ---------------------------------------------------------------------------
# current_user dependency (LEG-23)
# ---------------------------------------------------------------------------


def current_user(
    service: AuthService = Depends(get_auth_service),
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> User:
    """Resolve the session cookie to the authenticated User.

    Raises HTTP 401 if:
    - No session cookie is present
    - Session does not exist in the database
    - Session has expired
    """
    if session_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return service.get_user_from_session(session_id)


# ---------------------------------------------------------------------------
# require_permission dependency factory (LEG-39)
# ---------------------------------------------------------------------------


def require_permission(*permissions: Permission) -> Callable[..., User]:
    """Build a dependency that only lets the request through if the
    logged-in user's role has at least one of the given permissions.

    Usage: Depends(require_permission(Permission.CASE_SUBMIT_FOR_REVIEW))
           Depends(require_permission(Permission.CASE_READ_ANY, Permission.CASE_READ_ASSIGNED))

    Raises HTTP 403 if the role has none of the given permissions.
    Runs current_user first, so an unauthenticated request still gets 401,
    not 403.
    """
    required = set(permissions)

    def checker(user: User = Depends(current_user)) -> User:
        if not has_any_permission(user.role, required):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not permitted",
            )
        return user

    return checker


# ---------------------------------------------------------------------------
# POST /auth/login  (LEG-22)
# ---------------------------------------------------------------------------


@router.post("/login", response_model=LoginResponse)
def login(
    data: LoginRequest,
    response: Response,
    service: AuthService = Depends(get_auth_service),
) -> LoginResponse:
    """Verify credentials, create server-side session, set httpOnly cookie."""
    session_id, must_change_password = service.login(data)

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,  # not accessible via JS -- prevents XSS theft
        samesite="lax",  # CSRF protection for browser requests
        secure=False,  # set True in production (HTTPS only)
        max_age=60 * 60 * 24,  # 24 hours, matches SESSION_TTL_HOURS
    )

    return LoginResponse(
        message="Logged in successfully",
        must_change_password=must_change_password,
    )


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


# ---------------------------------------------------------------------------
# GET /auth/me  (LEG-23)
# ---------------------------------------------------------------------------


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(current_user)) -> User:
    """Return the currently authenticated user."""
    return user


# ---------------------------------------------------------------------------
# POST /auth/change-password  (LEG-21)
# ---------------------------------------------------------------------------


@router.post("/change-password", response_model=MessageResponse)
def change_password(
    data: ChangePasswordRequest,
    user: User = Depends(current_user),
    service: AuthService = Depends(get_auth_service),
) -> MessageResponse:
    """Change the current user's password.

    Works even if must_change_password is True -- this is how a user
    clears that flag after being given a temporary password by an admin.
    """
    service.change_password(user, data)
    return MessageResponse(message="Password changed successfully")
