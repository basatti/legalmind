from foundation.case_state_machine import CaseStateMachine
from foundation.models import CaseStatus


def test_legal_transitions():
    sm = CaseStateMachine()
    assert sm.can_transition(CaseStatus.OPEN, CaseStatus.IN_PROGRESS) == True
    assert sm.can_transition(CaseStatus.IN_PROGRESS, CaseStatus.CLOSED) == True


def test_illegal_transitions():
    sm = CaseStateMachine()
    assert sm.can_transition(CaseStatus.CLOSED, CaseStatus.OPEN) == False
    assert sm.can_transition(CaseStatus.OPEN, CaseStatus.CLOSED) == False
    assert sm.can_transition(CaseStatus.IN_PROGRESS, CaseStatus.OPEN) == False