"""Authentication business logic."""

from fastapi import HTTPException, status

from foundation.hashing import hash_password
from foundation.models import Role, User
from foundation.schemas import UserRegisterRequest
from repositories.user_repository import UserRepository


class AuthService:
    def __init__(self, user_repository: UserRepository):
        self.user_repository = user_repository

    def register(self, data: UserRegisterRequest) -> User:
        existing_user = self.user_repository.get_by_email(data.email)
        if existing_user is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email already exists",
            )

        new_user = User(
            email=data.email,
            full_name=data.full_name,
            hashed_password=hash_password(data.password),
            role=Role.USER,
        )

        return self.user_repository.add(new_user)
    