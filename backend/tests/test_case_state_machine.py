from foundation.case_state_machine import CaseStateMachine
from foundation.models import CaseStatus


def test_legal_transitions() -> None:
    sm = CaseStateMachine()
    assert sm.can_transition(CaseStatus.DRAFT, CaseStatus.IN_PROGRESS)
    assert sm.can_transition(CaseStatus.IN_PROGRESS, CaseStatus.SUBMITTED_FOR_REVIEW)
    assert sm.can_transition(CaseStatus.SUBMITTED_FOR_REVIEW, CaseStatus.UNDER_REVIEW)
    assert sm.can_transition(CaseStatus.UNDER_REVIEW, CaseStatus.REVISIONS_REQUESTED)
    assert sm.can_transition(CaseStatus.UNDER_REVIEW, CaseStatus.CLOSED)
    assert sm.can_transition(CaseStatus.REVISIONS_REQUESTED, CaseStatus.IN_PROGRESS)


def test_illegal_transitions() -> None:
    sm = CaseStateMachine()
    # Cannot skip states
    assert not sm.can_transition(CaseStatus.DRAFT, CaseStatus.CLOSED)
    assert not sm.can_transition(CaseStatus.DRAFT, CaseStatus.UNDER_REVIEW)
    # Cannot go backwards
    assert not sm.can_transition(CaseStatus.IN_PROGRESS, CaseStatus.DRAFT)
    assert not sm.can_transition(CaseStatus.CLOSED, CaseStatus.DRAFT)
    # Terminal state has no transitions
    assert not sm.can_transition(CaseStatus.CLOSED, CaseStatus.IN_PROGRESS)
