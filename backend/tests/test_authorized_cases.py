"""Tests for the retrieval authorization types and interfaces (LEG-64)."""

from dataclasses import FrozenInstanceError

import pytest

from foundation.authorization import (
    AllCases,
    AuthorizedCases,
    CaseReader,
    ChunkSearcher,
    TheseCases,
)
from foundation.models import DocumentChunk, Role, User


def user(role: Role) -> User:
    return User(id=1, email="x@y.sa", full_name="X", hashed_password="", role=role)


# --- the distinction this module exists for --------------------------------


def test_full_access_and_no_access_are_different_values() -> None:
    everything: AuthorizedCases = AllCases()
    nothing: AuthorizedCases = TheseCases(frozenset())

    print(f"Partner  -> {everything!r}")
    print(f"unassigned Paralegal -> {nothing!r}")

    assert everything != nothing


def test_full_access_carries_no_case_ids_to_misread() -> None:
    """AllCases has no case_ids at all — not an empty one."""
    assert not hasattr(AllCases(), "case_ids")


def test_restricted_access_to_nothing_is_a_legal_value() -> None:
    nothing = TheseCases(frozenset())
    print(f"case_ids = {sorted(nothing.case_ids)}")
    assert nothing.case_ids == frozenset()


# --- value semantics -------------------------------------------------------


def test_the_same_cases_compare_equal_regardless_of_order() -> None:
    assert TheseCases(frozenset({2, 1})) == TheseCases(frozenset({1, 2}))


def test_access_cannot_be_widened_after_it_is_computed() -> None:
    authorized = TheseCases(frozenset({1, 2}))

    with pytest.raises(FrozenInstanceError):
        authorized.case_ids = frozenset({1, 2, 99})  # type: ignore[misc]

    with pytest.raises(AttributeError):
        authorized.case_ids.add(99)  # type: ignore[attr-defined]

    print(f"unchanged: {sorted(authorized.case_ids)}")
    assert authorized.case_ids == frozenset({1, 2})


# --- the interfaces --------------------------------------------------------


class FakeCaseReader:
    """Everything a CaseReader must have, and nothing more."""

    def authorized_cases(self, user: User) -> AuthorizedCases:
        return AllCases()


class FakeChunkSearcher:
    def search(
        self,
        query_vector: list[float],
        within: AuthorizedCases,
        limit: int,
    ) -> list[DocumentChunk]:
        return []


def test_a_class_with_the_right_methods_satisfies_the_interfaces() -> None:
    assert isinstance(FakeCaseReader(), CaseReader)
    assert isinstance(FakeChunkSearcher(), ChunkSearcher)


def test_the_case_repository_does_not_satisfy_case_reader() -> None:
    """The point of ISP here: retrieval cannot be handed the write-capable
    repository by accident, because it does not fit the interface."""
    from repositories.case_repository import CaseRepository

    assert not isinstance(CaseRepository, CaseReader)


def test_a_reader_answers_with_one_of_the_two_kinds() -> None:
    answer = FakeCaseReader().authorized_cases(user(Role.PARTNER))
    print(f"reader returned {answer!r}")
    assert isinstance(answer, AllCases | TheseCases)
