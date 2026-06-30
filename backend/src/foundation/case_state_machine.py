from foundation.models import CaseStatus


class CaseStateMachine:
    TRANSITIONS: dict[CaseStatus, list[CaseStatus]] = {
        CaseStatus.OPEN: [CaseStatus.IN_PROGRESS],
        CaseStatus.IN_PROGRESS: [CaseStatus.CLOSED],
        CaseStatus.CLOSED: [],
    }

    def can_transition(self, from_state: CaseStatus, to_state: CaseStatus) -> bool:
        return to_state in self.TRANSITIONS.get(from_state, [])
