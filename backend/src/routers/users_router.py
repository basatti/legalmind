"""Admin-only user management endpoints (LEG-21)."""

from fastapi import APIRouter, Depends, status
from sqlmodel import Session

from foundation.database import get_session
from foundation.models import User
from foundation.permissions import Permission
from foundation.schemas import UserCreateRequest, UserResponse
from repositories.session_repository import SessionRepository
from repositories.user_repository import UserRepository
from routers.auth_router import require_permission
from services.auth_service import AuthService

router = APIRouter(prefix="/users", tags=["users"])


def get_auth_service(session: Session = Depends(get_session)) -> AuthService:
    return AuthService(
        user_repository=UserRepository(session),
        session_repository=SessionRepository(session),
    )


def get_user_repository(session: Session = Depends(get_session)) -> UserRepository:
    return UserRepository(session)


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    data: UserCreateRequest,
    service: AuthService = Depends(get_auth_service),
    _user: User = Depends(require_permission(Permission.USER_MANAGE)),
) -> User:
    """Create a new user with a temporary password. Admin-only.

    There is no public signup -- every account is created this way.
    The new user must change their password on first login.
    """
    return service.create_user(data)


@router.get("/", response_model=list[UserResponse])
def list_users(
    repository: UserRepository = Depends(get_user_repository),
    _user: User = Depends(
        require_permission(Permission.USER_MANAGE, Permission.CASE_ASSIGN)
    ),
) -> list[User]:
    """List all users. Admin, or Partner (to pick who to assign to a case)."""
    return repository.get_all()
