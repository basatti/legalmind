"""Assignment repository — queries the user↔case bipartite graph.

The Assignment table is the edge list of the bipartite graph:
    Users ──── Assignment ──── Cases

Two core queries:
  - is_assigned(user_id, case_id): is there an edge between this user and case? O(log n) via index
  - get_case_ids_for_user(user_id): which case nodes does this user connect to? O(log n) via index
"""

from sqlmodel import Session, select

from foundation.models import Assignment


class AssignmentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def is_assigned(self, user_id: int, case_id: int) -> bool:
        """Return True if an edge exists between user_id and case_id.

        Uses indexed foreign keys — O(log n), not a full table scan.
        """
        result = self.session.exec(
            select(Assignment).where(
                Assignment.user_id == user_id,
                Assignment.case_id == case_id,
            )
        ).first()
        return result is not None

    def get_case_ids_for_user(self, user_id: int) -> list[int]:
        """Return all case_ids this user is assigned to.

        Uses ix_assignment_user_id index — O(log n).
        """
        results = self.session.exec(
            select(Assignment.case_id).where(Assignment.user_id == user_id)
        ).all()
        return list(results)

    def add(self, assignment: Assignment) -> Assignment:
        """Create a new edge between a user and a case."""
        self.session.add(assignment)
        self.session.commit()
        self.session.refresh(assignment)
        return assignment
