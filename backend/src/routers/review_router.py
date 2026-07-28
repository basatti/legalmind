from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from foundation.database import get_session
from foundation.models import Feedback, Review, User
from foundation.permissions import Permission
from foundation.schemas import (
    FeedbackReplyRequest,
    FeedbackResponse,
    ReviewCreateRequest,
    ReviewResponse,
)
from repositories.assignment_repository import AssignmentRepository
from repositories.case_repository import CaseRepository
from repositories.feedback_repository import FeedbackRepository
from repositories.review_repository import ReviewRepository
from routers.auth_router import require_permission
from services.case_service import IllegalTransitionError
from services.review_service import ReviewService

router = APIRouter(prefix="/cases/{case_id}", tags=["reviews"])


def get_review_service(session: Session = Depends(get_session)) -> ReviewService:
    return ReviewService(
        review_repository=ReviewRepository(session),
        feedback_repository=FeedbackRepository(session),
        case_repository=CaseRepository(session),
        assignment_repository=AssignmentRepository(session),
    )


@router.post("/reviews", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
def create_review(
    case_id: int,
    data: ReviewCreateRequest,
    service: ReviewService = Depends(get_review_service),
    user: User = Depends(require_permission(Permission.CASE_REVIEW)),
) -> Feedback:
    """Partner opens a review round and leaves the first comment."""
    try:
        return service.create_review(case_id, data, user)
    except IllegalTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post("/feedback", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
def respond_to_feedback(
    case_id: int,
    data: FeedbackReplyRequest,
    service: ReviewService = Depends(get_review_service),
    user: User = Depends(
        require_permission(Permission.CASE_EDIT_ANY, Permission.CASE_EDIT_ASSIGNED)
    ),
) -> Feedback:
    """Attorney (or Partner/Admin) replies to a specific feedback comment."""
    return service.respond_to_feedback(case_id, data, user)


@router.get("/reviews", response_model=list[ReviewResponse])
def list_reviews(
    case_id: int,
    service: ReviewService = Depends(get_review_service),
    user: User = Depends(
        require_permission(Permission.CASE_READ_ANY, Permission.CASE_READ_ASSIGNED)
    ),
) -> list[Review]:
    """List every review round opened on this case."""
    return service.list_reviews(case_id, user)


@router.get("/feedback", response_model=list[FeedbackResponse])
def list_feedback(
    case_id: int,
    service: ReviewService = Depends(get_review_service),
    user: User = Depends(
        require_permission(Permission.CASE_READ_ANY, Permission.CASE_READ_ASSIGNED)
    ),
) -> list[Feedback]:
    """List every feedback comment across all review rounds on this case."""
    return service.list_feedback(case_id, user)


@router.post("/feedback/{feedback_id}/resolve", response_model=FeedbackResponse)
def resolve_feedback(
    case_id: int,
    feedback_id: int,
    service: ReviewService = Depends(get_review_service),
    user: User = Depends(
        require_permission(Permission.CASE_EDIT_ANY, Permission.CASE_EDIT_ASSIGNED)
    ),
) -> Feedback:
    """Attorney (or Partner/Admin) marks a feedback item resolved."""
    return service.resolve_feedback(case_id, feedback_id, user)
