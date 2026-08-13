from datetime import datetime

from sqlmodel import Session, col, select

from foundation.models import Session as SessionModel


class SessionRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, session_model: SessionModel) -> SessionModel:
        self.session.add(session_model)
        self.session.commit()
        self.session.refresh(session_model)
        return session_model

    def get_by_id(self, session_id: str) -> SessionModel | None:
        return self.session.get(SessionModel, session_id)

    def delete(self, session_id: str) -> None:
        session_model = self.session.get(SessionModel, session_id)
        if session_model:
            self.session.delete(session_model)
            self.session.commit()

    def delete_for_user(self, user_id: int, keep_session_id: str | None) -> int:
        """Delete every session belonging to `user_id`, sparing one. Returns how many.

        `keep_session_id` is the session making the request that triggered this.
        Changing a password is the case that needs it: the point is to evict
        whoever else is holding a session, and evicting the person doing the
        evicting as well would throw a new user straight back to the login
        screen in the middle of setting their first real password.

        Passing `None` spares nothing and clears the account out entirely. It is
        the safer direction of the two, so it is what an unset value means
        rather than something a caller has to ask for -- but the parameter has
        no default, because "am I keeping this session or not" is a question
        every caller should have to answer out loud.
        """
        statement = select(SessionModel).where(col(SessionModel.user_id) == user_id)

        if keep_session_id is not None:
            statement = statement.where(col(SessionModel.id) != keep_session_id)

        doomed = list(self.session.exec(statement).all())

        for session_model in doomed:
            self.session.delete(session_model)

        self.session.commit()

        return len(doomed)

    def delete_expired(self, now: datetime) -> int:
        """Remove every session that expired before `now`. Returns how many.

        Expiry was enforced only on read: `AuthService.get_user_from_session`
        deletes a session when someone presents an expired one. That is correct
        but incomplete — a user who logs in and never returns leaves a row that
        nothing ever visits again, so the table only ever grows.

        `now` is a parameter rather than `datetime.now()` because a sweep that
        reads its own clock cannot be tested without patching time. The caller
        already knows what time it is.

        Rows are loaded and deleted rather than removed by a single bulk
        statement. At this project's scale the difference is nothing, and it
        keeps the method inside the typed SQLModel API instead of reaching for
        `execute()` and an untyped `rowcount`. If the session table ever grows
        enough for that to matter, this is the line to change.
        """
        statement = select(SessionModel).where(col(SessionModel.expires_at) < now)
        expired = list(self.session.exec(statement).all())

        for session_model in expired:
            self.session.delete(session_model)

        # One commit for the whole sweep: a partial delete is not a state worth
        # leaving behind, and every row here is equally dead.
        self.session.commit()

        return len(expired)
