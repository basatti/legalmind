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
