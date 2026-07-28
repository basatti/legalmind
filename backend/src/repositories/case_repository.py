from sqlmodel import Session, select

from foundation.models import Case


class CaseRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, case: Case) -> Case:
        self.session.add(case)
        self.session.commit()
        self.session.refresh(case)
        return case

    def get_all(self) -> list[Case]:
        return list(self.session.exec(select(Case)).all())

    def get_by_ids(self, case_ids: list[int]) -> list[Case]:
        """Return only cases whose id is in the given list.

        Used for assignment-scoped listing — fetches only the cases
        a user is assigned to. O(log n) per id via primary key index.
        """
        if not case_ids:
            return []
        return list(
            self.session.exec(select(Case).where(Case.id.in_(case_ids))).all()  # type: ignore[union-attr]
        )

    def get_by_id(self, case_id: int) -> Case | None:
        return self.session.get(Case, case_id)

    def update(self, case: Case) -> Case:
        self.session.add(case)
        self.session.commit()
        self.session.refresh(case)
        return case
