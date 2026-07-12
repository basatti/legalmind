"""Authentication business logic."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status

from foundation.hashing import hash_password, verify_password
from foundation.models import Session as SessionModel
from foundation.models import User
from foundation.schemas import LoginRequest, UserRegisterRequest
from repositories.session_repository import SessionRepository
from repositories.user_repository import UserRepository

# Session lifetime — 24 hours
SESSION_TTL_HOURS = 24


class AuthService:
    def __init__(
        self,
        user_repository: UserRepository,
        session_repository: SessionRepository,
    ):
        self.user_repository = user_repository
        self.session_repository = session_repository

    # ------------------------------------------------------------------
    # Registration (LEG-21, unchanged)
    # ------------------------------------------------------------------

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
            role=data.role,
        )

        return self.user_repository.add(new_user)

    # ------------------------------------------------------------------
    # Login — verify credentials, create session, return session id
    # ------------------------------------------------------------------

    def login(self, data: LoginRequest) -> str:
        """Verify credentials and create a server-side session.

        Returns the session id to be set as an httpOnly cookie.
        Raises HTTP 401 for invalid credentials.
        """
        user = self.user_repository.get_by_email(data.email)

        # Use the same error for wrong email AND wrong password
        # to avoid leaking whether the email exists (user enumeration attack)
        if user is None or not verify_password(data.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is inactive",
            )

        session = SessionModel(
            id=str(uuid.uuid4()),
            user_id=user.id,
            expires_at=datetime.now(UTC) + timedelta(hours=SESSION_TTL_HOURS),
        )

        self.session_repository.add(session)
        return session.id

    # ------------------------------------------------------------------
    # Logout — invalidate session
    # ------------------------------------------------------------------

    def logout(self, session_id: str) -> None:
        """Delete the session from the store, invalidating it immediately."""
        self.session_repository.delete(session_id)

    # ------------------------------------------------------------------
    # Session validation — used by current_user dependency (LEG-23)
    # ------------------------------------------------------------------

    def get_user_from_session(self, session_id: str) -> User:
        """Resolve a session id to its User.

        Raises HTTP 401 if the session is missing or expired.
        """
        session = self.session_repository.get_by_id(session_id)

        if session is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session not found",
            )

        if datetime.now(UTC) > session.expires_at.replace(tzinfo=UTC):
            self.session_repository.delete(session_id)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired",
            )

        user: User | None = self.user_repository.get_by_id(session.user_id)

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )

        return user
