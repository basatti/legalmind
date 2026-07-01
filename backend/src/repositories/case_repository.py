from sqlmodel import Session, select

from foundation.models import Case


class CaseRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, case: Case) -> Case:
        self.session.add(case)
        self.session.commit()
        self.session.refresh(case)
        return case

    def get_all(self) -> list[Case]:
        return list(self.session.exec(select(Case)).all())
