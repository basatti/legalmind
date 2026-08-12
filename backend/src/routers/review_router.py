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
from repositories.user_repository import UserRepository
from routers.auth_router import require_permission
from services.case_service import IllegalTransitionError
from services.review_service import ReviewService

router = APIRouter(prefix="/cases/{case_id}", tags=["reviews"])

UNKNOWN_AUTHOR = "Unknown user"
"""Shown when a comment's author no longer has a row.

Deleting a user does not delete what they wrote — the thread is a record of a
review, and removing half a conversation would misrepresent it. So the comment
survives with a name that says plainly that the person is gone, rather than a
blank or a crash.
"""


def get_user_repository(session: Session = Depends(get_session)) -> UserRepository:
    return UserRepository(session)


def _present(feedback: Feedback, authors: dict[int, User]) -> FeedbackResponse:
    """Attach the author's name to one comment.

    Authors are passed in already looked up, so rendering a thread of any size
    costs one query rather than one per comment.
    """
    author = authors.get(feedback.author_id)

    return FeedbackResponse(
        id=feedback.id if feedback.id is not None else 0,
        review_id=feedback.review_id,
        author_id=feedback.author_id,
        author_name=author.full_name if author else UNKNOWN_AUTHOR,
        content=feedback.content,
        parent_id=feedback.parent_id,
        created_at=feedback.created_at,
        resolved=feedback.resolved,
    )


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
    users: UserRepository = Depends(get_user_repository),
) -> FeedbackResponse:
    """Partner opens a review round and leaves the first comment."""
    try:
        feedback = service.create_review(case_id, data, user)
    except IllegalTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return _present(feedback, users.get_by_ids([feedback.author_id]))


@router.post("/feedback", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
def respond_to_feedback(
    case_id: int,
    data: FeedbackReplyRequest,
    service: ReviewService = Depends(get_review_service),
    user: User = Depends(
        require_permission(Permission.CASE_EDIT_ANY, Permission.CASE_EDIT_ASSIGNED)
    ),
    users: UserRepository = Depends(get_user_repository),
) -> FeedbackResponse:
    """Attorney (or Partner/Admin) replies to a specific feedback comment."""
    feedback = service.respond_to_feedback(case_id, data, user)

    return _present(feedback, users.get_by_ids([feedback.author_id]))


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
    users: UserRepository = Depends(get_user_repository),
) -> list[FeedbackResponse]:
    """List every feedback comment across all review rounds on this case."""
    thread = service.list_feedback(case_id, user)
    authors = users.get_by_ids(item.author_id for item in thread)

    return [_present(item, authors) for item in thread]


@router.post("/feedback/{feedback_id}/resolve", response_model=FeedbackResponse)
def resolve_feedback(
    case_id: int,
    feedback_id: int,
    service: ReviewService = Depends(get_review_service),
    user: User = Depends(
        require_permission(Permission.CASE_EDIT_ANY, Permission.CASE_EDIT_ASSIGNED)
    ),
    users: UserRepository = Depends(get_user_repository),
) -> FeedbackResponse:
    """Attorney (or Partner/Admin) marks a feedback item resolved."""
    feedback = service.resolve_feedback(case_id, feedback_id, user)

    return _present(feedback, users.get_by_ids([feedback.author_id]))
