"""Authentication business logic."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status

from foundation.hashing import hash_password, verify_password
from foundation.models import Session as SessionModel
from foundation.models import User
from foundation.schemas import ChangePasswordRequest, LoginRequest, UserCreateRequest
from repositories.session_repository import SessionRepository
from repositories.user_repository import UserRepository

# Session lifetime -- 24 hours
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
    # Admin-only user creation (LEG-21) -- replaces public registration
    # ------------------------------------------------------------------

    def create_user(self, data: UserCreateRequest) -> User:
        existing_user = self.user_repository.get_by_email(data.email)
        if existing_user is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email already exists",
            )

        new_user = User(
            email=data.email,
            full_name=data.full_name,
            hashed_password=hash_password(data.temporary_password),
            role=data.role,
            must_change_password=True,
        )

        return self.user_repository.add(new_user)

    # ------------------------------------------------------------------
    # Login -- verify credentials, create session, return session id
    # ------------------------------------------------------------------

    def login(self, data: LoginRequest) -> tuple[str, bool]:
        """Verify credentials and create a server-side session.

        Returns (session_id, must_change_password).
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
        return session.id, user.must_change_password

    # ------------------------------------------------------------------
    # Logout -- invalidate session
    # ------------------------------------------------------------------

    def logout(self, session_id: str) -> None:
        """Delete the session from the store, invalidating it immediately."""
        self.session_repository.delete(session_id)

    # ------------------------------------------------------------------
    # Session validation -- used by current_user dependency (LEG-23)
    # ------------------------------------------------------------------

    def get_user_from_session(self, session_id: str) -> User:
        """Resolve a session id to its User.

        Raises HTTP 401 if the session is missing, expired, or belongs to an
        account that has since been switched off.
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

        if not user.is_active:
            # The same check `login` makes, made again on every request.
            #
            # Reading it only at login meant switching an account off did
            # nothing to anyone already holding a session: the row stays valid,
            # this lookup keeps handing the user back, and they carry on working
            # until the 24-hour expiry runs out on its own. A switch that is
            # only read once is not a switch, it is a note about the past.
            #
            # 401 rather than the 403 `login` returns, because the two are
            # answering different questions. At login the client is asking to be
            # let in and can be told why it was refused. Here the client is
            # presenting a credential that no longer identifies anyone allowed
            # in -- the same situation as the expired session above, which is
            # why it gets the same answer.
            #
            # What the frontend does with it is only half joined up, and the
            # gap is there rather than here: `AuthProvider` reads the session
            # once on mount, so a 401 from *this* branch sends someone to the
            # login page on their next page load, while a 401 from a call made
            # by an already-open page surfaces as an error state instead. The
            # door is shut either way -- every request is refused from this
            # moment on -- but the person is not told why until they reload.
            # Fixing that means teaching the API client to clear the user on
            # any 401, and it is a frontend change, not a reason to pick a
            # different status code here.
            #
            # The row is deleted for the same reason the expired branch deletes
            # its own: it can never be used again, so leaving it for the reaper
            # to find an hour later serves nobody. Only this session goes -- the
            # account's others die the same way the moment they are used.
            self.session_repository.delete(session_id)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account is inactive",
            )

        return user

    # ------------------------------------------------------------------
    # Change password (LEG-21) -- required on first login, or any time after
    # ------------------------------------------------------------------

    def change_password(
        self,
        user: User,
        data: ChangePasswordRequest,
        current_session_id: str | None,
    ) -> None:
        """Verify the current password, set the new one, and evict every other session.

        Clears must_change_password so the user is no longer forced
        to change it again.

        The eviction is the part that is easy to leave out, and leaving it out
        is worse than not offering the feature. A password is how someone *asks
        for* a session; it is not stored in one and never looked at again after
        login. So changing it stopped future logins with the old password and
        did nothing whatsoever to sessions already handed out -- which means
        someone who changed their password because they believed another person
        was in their account was told "Password changed successfully" while that
        person carried on reading case files until the 24-hour expiry. The wrong
        answer here is not a missing feature, it is false reassurance.

        `current_session_id` is spared, so the person doing this stays logged in
        -- see `SessionRepository.delete_for_user` for why that is not merely a
        convenience.
        """
        if not verify_password(data.current_password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Current password is incorrect",
            )

        user.hashed_password = hash_password(data.new_password)
        user.must_change_password = False
        self.user_repository.update(user)

        # After the write, not before: if this somehow fails, the password has
        # still genuinely changed, and the sessions it did not reach are the
        # ones that were already going to expire on their own. The reverse order
        # would evict everybody and then possibly not change the password.
        assert user.id is not None
        self.session_repository.delete_for_user(user.id, keep_session_id=current_session_id)
