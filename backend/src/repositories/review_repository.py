from sqlmodel import Session

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
