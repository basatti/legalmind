from collections.abc import Iterable

from sqlmodel import Session, col, select

from foundation.models import User


class UserRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_email(self, email: str) -> User | None:
        return self.session.exec(select(User).where(User.email == email)).first()

    def get_by_id(self, user_id: int) -> User | None:
        return self.session.get(User, user_id)

    def get_by_ids(self, user_ids: Iterable[int]) -> dict[int, User]:
        """Look up several users at once, keyed by id.

        One query for a whole feedback thread rather than one per comment. An
        id with no row is simply absent from the result — the caller decides
        what a missing author means, which is not a repository's business.
        """
        unique = list(set(user_ids))
        if not unique:
            return {}

        statement = select(User).where(col(User.id).in_(unique))
        return {user.id: user for user in self.session.exec(statement) if user.id is not None}

    def get_all(self) -> list[User]:
        return list(self.session.exec(select(User)).all())

    def add(self, user: User) -> User:
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return user

    def update(self, user: User) -> User:
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return user
