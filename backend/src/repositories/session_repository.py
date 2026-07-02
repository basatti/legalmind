from sqlmodel import Session

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
