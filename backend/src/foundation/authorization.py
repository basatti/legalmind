"""Who is allowed to see which cases, expressed as a value a query can use.

Authorization already exists in this codebase: permissions.py says what a role
may do, and the Assignment table says which cases a person is attached to. What
does not exist yet is a single value answering "which cases may this user draw
answers from", in a form a database query can be built from.

CaseService.list_cases answers that question by branching into two different
calls — get_all() for Partners, get_by_ids() for everyone else. Retrieval cannot
do that: it runs one query, so the answer has to arrive as one value. This module
gives that value a shape in which the two possibilities stay distinguishable.
"""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from foundation.models import DocumentChunk, User


@dataclass(frozen=True)
class AllCases:
    """The user may draw on every case in the system.

    Carries no case ids on purpose. Partners and Admins hold case:read:any and
    have no Assignment rows at all, so listing their ids would mean reading every
    id in the table to express something the role already states outright.
    """


@dataclass(frozen=True)
class TheseCases:
    """The user may draw only on the cases listed here.

    An empty set is a legitimate value with one unambiguous meaning: this user is
    assigned to nothing and may see nothing. That is precisely the case that was
    indistinguishable from AllCases while both were expressed as an empty list.
    """

    case_ids: frozenset[int]


AuthorizedCases = AllCases | TheseCases
"""Every user's access is exactly one of these two — never both, never neither."""


@runtime_checkable
class CaseReader(Protocol):
    """Reads case access. No writes, no exports, nothing else."""

    def authorized_cases(self, user: User) -> AuthorizedCases:
        """Which cases this user may draw answers from."""
        ...


@runtime_checkable
class ChunkSearcher(Protocol):
    """Searches stored chunks, within a set of cases the caller has authorised."""

    def search(
        self,
        query_vector: list[float],
        within: AuthorizedCases,
        limit: int,
    ) -> list[DocumentChunk]:
        """The `limit` closest chunks to query_vector, from `within` only.

        Takes `within` rather than case ids so the restriction and the search are
        the same call — an implementation has no way to run the search first and
        filter afterwards.
        """
        ...
