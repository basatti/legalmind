from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from foundation.database import get_session
from foundation.models import Case, CaseStatus, User
from foundation.permissions import Permission, has_any_permission
from foundation.schemas import (
    CaseCreateRequest,
    CaseTransitionRequest,
    CaseUpdateRequest,
)
from repositories.assignment_repository import AssignmentRepository
from repositories.case_repository import CaseRepository
from routers.auth_router import current_user, require_permission
from services.case_service import CaseService, IllegalTransitionError

router = APIRouter(prefix="/cases", tags=["cases"])

# target status -> permissions allowed to make that transition (any one suffices)
TRANSITION_PERMISSIONS: dict[CaseStatus, tuple[Permission, ...]] = {
    CaseStatus.IN_PROGRESS: (Permission.CASE_EDIT_ANY, Permission.CASE_EDIT_ASSIGNED),
    CaseStatus.SUBMITTED_FOR_REVIEW: (Permission.CASE_SUBMIT_FOR_REVIEW,),
    CaseStatus.UNDER_REVIEW: (Permission.CASE_REVIEW,),
    CaseStatus.REVISIONS_REQUESTED: (Permission.CASE_REVIEW,),
    CaseStatus.CLOSED: (Permission.CASE_CLOSE,),
}


def get_case_service(session: Session = Depends(get_session)) -> CaseService:
    return CaseService(
        repository=CaseRepository(session),
        assignment_repository=AssignmentRepository(session),
    )


def require_transition_permission(
    data: CaseTransitionRequest,
    user: User = Depends(current_user),
) -> User:
    """Look up which permission this specific target_status requires,
    then check the logged-in user's role has it."""
    required = TRANSITION_PERMISSIONS.get(data.target_status)
    if required is not None and not has_any_permission(user.role, set(required)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not permitted",
        )
    return user


@router.get("/")
def list_cases(
    service: CaseService = Depends(get_case_service),
    user: User = Depends(
        require_permission(Permission.CASE_READ_ANY, Permission.CASE_READ_ASSIGNED)
    ),
) -> list[Case]:
    return service.list_cases(user)


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_case(
    data: CaseCreateRequest,
    service: CaseService = Depends(get_case_service),
    _user: User = Depends(require_permission(Permission.CASE_CREATE)),
) -> Case:
    return service.create_case(data)


@router.get("/{case_id}")
def get_case(
    case_id: int,
    service: CaseService = Depends(get_case_service),
    user: User = Depends(
        require_permission(Permission.CASE_READ_ANY, Permission.CASE_READ_ASSIGNED)
    ),
) -> Case:
    return service.get_case(case_id, user)


@router.patch("/{case_id}")
def update_case(
    case_id: int,
    data: CaseUpdateRequest,
    service: CaseService = Depends(get_case_service),
    user: User = Depends(
        require_permission(Permission.CASE_EDIT_ANY, Permission.CASE_EDIT_ASSIGNED)
    ),
) -> Case:
    return service.update_case(case_id, data, user)


@router.post("/{case_id}/transition")
def transition_case(
    case_id: int,
    data: CaseTransitionRequest,
    service: CaseService = Depends(get_case_service),
    user: User = Depends(require_transition_permission),
) -> Case:
    try:
        return service.transition_status(case_id, data.target_status, user)
    except IllegalTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
