from sqlmodel import Session, select

from foundation.models import Feedback, Review


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

    def list_by_case(self, case_id: int) -> list[Feedback]:
        """All feedback across every review round on this case."""
        results = self.session.exec(
            select(Feedback).join(Review).where(Review.case_id == case_id)
        ).all()
        return list(results)

    def mark_resolved(self, feedback_id: int) -> Feedback:
        feedback = self.session.get(Feedback, feedback_id)
        assert feedback is not None
        feedback.resolved = True
        self.session.add(feedback)
        self.session.commit()
        self.session.refresh(feedback)
        return feedback
