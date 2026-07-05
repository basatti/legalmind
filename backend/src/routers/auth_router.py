"""Authentication endpoints."""

from fastapi import APIRouter, Depends, status
from sqlmodel import Session

from foundation.database import get_session
from foundation.schemas import UserRegisterRequest, UserResponse
from repositories.user_repository import UserRepository
from foundation.models import User
from services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def get_auth_service(session: Session = Depends(get_session)) -> AuthService:
    return AuthService(UserRepository(session))


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(
    data: UserRegisterRequest,
    service: AuthService = Depends(get_auth_service),
) -> User:
    return service.register(data)
