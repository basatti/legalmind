from sqlmodel import Session

from foundation.models import Feedback


class FeedbackRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, feedback: Feedback) -> Feedback:
        self.session.add(feedback)
        self.session.commit()
        self.session.refresh(feedback)
        return feedback

    def get_by_id(self, feedback_id: int) -> Feedback | None:
        return self.session.get(Feedback, feedback_id)
