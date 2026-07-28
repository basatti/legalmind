"""Review + threaded feedback business logic (LEG-52, LEG-54)."""

from fastapi import HTTPException, status

from foundation.case_state_machine import CaseStateMachine
from foundation.models import Case, CaseStatus, Feedback, Review, User
from foundation.permissions import Permission, has_permission
from foundation.schemas import FeedbackReplyRequest, ReviewCreateRequest
from repositories.assignment_repository import AssignmentRepository
from repositories.case_repository import CaseRepository
from repositories.feedback_repository import FeedbackRepository
from repositories.review_repository import ReviewRepository
from services.case_service import IllegalTransitionError


class ReviewService:
    def __init__(
        self,
        review_repository: ReviewRepository,
        feedback_repository: FeedbackRepository,
        case_repository: CaseRepository,
        assignment_repository: AssignmentRepository,
    ) -> None:
        self.review_repository = review_repository
        self.feedback_repository = feedback_repository
        self.case_repository = case_repository
        self.assignment_repository = assignment_repository
        self.state_machine = CaseStateMachine()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_case_or_404(self, case_id: int) -> Case:
        case = self.case_repository.get_by_id(case_id)
        if case is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Case not found",
            )
        return case

    def _assert_can_respond(self, user: User, case: Case) -> None:
        """Only the assigned attorney (or a Partner/Admin) may respond."""
        if has_permission(user.role, Permission.CASE_EDIT_ANY):
            return

        assert user.id is not None
        if not self.assignment_repository.is_assigned(user.id, case.id):  # type: ignore[arg-type]
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not assigned to this case",
            )

    def _assert_can_read(self, user: User, case: Case) -> None:
        """Same read rule as case_service._assert_can_read: CASE_READ_ANY
        bypasses, everyone else must be assigned to the case."""
        if has_permission(user.role, Permission.CASE_READ_ANY):
            return

        assert user.id is not None
        if not self.assignment_repository.is_assigned(user.id, case.id):  # type: ignore[arg-type]
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not assigned to this case",
            )

    # ------------------------------------------------------------------
    # Partner: open a review round + leave the first comment
    # ------------------------------------------------------------------

    def create_review(self, case_id: int, data: ReviewCreateRequest, user: User) -> Feedback:
        case = self._get_case_or_404(case_id)

        target = CaseStatus.UNDER_REVIEW
        if not self.state_machine.can_transition(case.status, target):
            allowed = self.state_machine.allowed_next(case.status)
            raise IllegalTransitionError(case.status, target, allowed)

        assert user.id is not None
        review = self.review_repository.add(Review(case_id=case_id, reviewer_id=user.id))
        feedback = self.feedback_repository.add(
            Feedback(
                review_id=review.id,
                author_id=user.id,
                content=data.content,
                parent_id=None,
            )
        )

        case.status = target
        self.case_repository.update(case)

        return feedback

    # ------------------------------------------------------------------
    # Attorney: reply to a specific feedback comment
    # ------------------------------------------------------------------

    def respond_to_feedback(self, case_id: int, data: FeedbackReplyRequest, user: User) -> Feedback:
        case = self._get_case_or_404(case_id)
        self._assert_can_respond(user, case)

        parent = self.feedback_repository.get_by_id(data.parent_id)
        if parent is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Feedback not found",
            )

        review = self.review_repository.get_by_id(parent.review_id)
        if review is None or review.case_id != case_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Feedback does not belong to this case",
            )

        assert user.id is not None
        return self.feedback_repository.add(
            Feedback(
                review_id=parent.review_id,
                author_id=user.id,
                content=data.content,
                parent_id=data.parent_id,
            )
        )

    # ------------------------------------------------------------------
    # LEG-54: Attorney (or Partner/Admin) marks a feedback item resolved
    # ------------------------------------------------------------------

    def resolve_feedback(self, case_id: int, feedback_id: int, user: User) -> Feedback:
        case = self._get_case_or_404(case_id)
        self._assert_can_respond(user, case)

        feedback = self.feedback_repository.get_by_id(feedback_id)
        if feedback is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Feedback not found",
            )

        review = self.review_repository.get_by_id(feedback.review_id)
        if review is None or review.case_id != case_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Feedback does not belong to this case",
            )

        return self.feedback_repository.mark_resolved(feedback_id)

    # ------------------------------------------------------------------
    # LEG-54: Read the review/feedback thread for a case
    # ------------------------------------------------------------------

    def list_reviews(self, case_id: int, user: User) -> list[Review]:
        case = self._get_case_or_404(case_id)
        self._assert_can_read(user, case)
        return self.review_repository.list_by_case(case_id)

    def list_feedback(self, case_id: int, user: User) -> list[Feedback]:
        case = self._get_case_or_404(case_id)
        self._assert_can_read(user, case)
        return self.feedback_repository.list_by_case(case_id)
