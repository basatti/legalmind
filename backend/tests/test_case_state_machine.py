from foundation.case_state_machine import CaseStateMachine
from foundation.models import CaseStatus


def test_legal_transitions():
    sm = CaseStateMachine()
    assert sm.can_transition(CaseStatus.OPEN, CaseStatus.IN_PROGRESS)
    assert sm.can_transition(CaseStatus.IN_PROGRESS, CaseStatus.CLOSED)


def test_illegal_transitions():
    sm = CaseStateMachine()
    assert not sm.can_transition(CaseStatus.CLOSED, CaseStatus.OPEN)
    assert not sm.can_transition(CaseStatus.OPEN, CaseStatus.CLOSED)
    assert not sm.can_transition(CaseStatus.IN_PROGRESS, CaseStatus.OPEN)
