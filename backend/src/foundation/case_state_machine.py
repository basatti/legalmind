"""Case finite state machine.

Transition table (adjacency list representation):

    DRAFT ──────────────────────────────► IN_PROGRESS
    IN_PROGRESS ────────────────────────► SUBMITTED_FOR_REVIEW
    SUBMITTED_FOR_REVIEW ───────────────► UNDER_REVIEW
    UNDER_REVIEW ───────────────────────► REVISIONS_REQUESTED
                 ───────────────────────► CLOSED
    REVISIONS_REQUESTED ────────────────► IN_PROGRESS   (back for rework)
    CLOSED ─────────────────────────────► (terminal — no transitions)

This is a hand-coded FSM: the TRANSITIONS dict is the transition table,
can_transition() is the acceptance check. Any transition not listed is
illegal and will be rejected by CaseService.
"""

from foundation.models import CaseStatus


class CaseStateMachine:
    # Transition table: current_state → allowed next states
    TRANSITIONS: dict[CaseStatus, list[CaseStatus]] = {
        CaseStatus.DRAFT: [
            CaseStatus.IN_PROGRESS,
        ],
        CaseStatus.IN_PROGRESS: [
            CaseStatus.SUBMITTED_FOR_REVIEW,
        ],
        CaseStatus.SUBMITTED_FOR_REVIEW: [
            CaseStatus.UNDER_REVIEW,
        ],
        CaseStatus.UNDER_REVIEW: [
            CaseStatus.REVISIONS_REQUESTED,
            CaseStatus.CLOSED,
        ],
        CaseStatus.REVISIONS_REQUESTED: [
            CaseStatus.IN_PROGRESS,  # sent back for rework
        ],
        CaseStatus.CLOSED: [],  # terminal state — no outgoing transitions
    }

    def can_transition(self, from_state: CaseStatus, to_state: CaseStatus) -> bool:
        """Return True if the transition from_state → to_state is legal."""
        return to_state in self.TRANSITIONS.get(from_state, [])

    def allowed_next(self, from_state: CaseStatus) -> list[CaseStatus]:
        """Return all legal next states from the given state."""
        return self.TRANSITIONS.get(from_state, [])
