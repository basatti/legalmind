from sqlmodel import Session, select

from foundation.models import Review


class ReviewRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, review: Review) -> Review:
        self.session.add(review)
        self.session.commit()
        self.session.refresh(review)
        return review

    def get_by_id(self, review_id: int) -> Review | None:
        return self.session.get(Review, review_id)

    def list_by_case(self, case_id: int) -> list[Review]:
        results = self.session.exec(select(Review).where(Review.case_id == case_id)).all()
        return list(results)
