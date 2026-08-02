"""RAG query service (LEG-14).

Depends on CaseReader (LEG-64), not a repository, so retrieval code can never
be handed anything with write/export capability by accident (ISP).
"""

from foundation.authorization import CaseReader, TheseCases
from foundation.models import User
from foundation.schemas import QueryAskResponse


class RagService:
    def __init__(self, case_reader: CaseReader) -> None:
        self.case_reader = case_reader

    def ask(self, question: str, user: User) -> QueryAskResponse:
        authorized = self.case_reader.authorized_cases(user)

        if isinstance(authorized, TheseCases) and not authorized.case_ids:
            # Genuinely nothing this user is authorized to search — a clean
            # "no answer", not an error (LEG-65).
            return QueryAskResponse(answer=None)

        # Retrieval + grounded generation land in LEG-62/LEG-63. Until then,
        # there is authorized ground to search but nothing yet to search it
        # with — that is a 501, not a fabricated answer.
        raise NotImplementedError("Retrieval is not implemented yet (LEG-62/LEG-63)")
