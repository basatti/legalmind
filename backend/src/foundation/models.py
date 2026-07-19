from datetime import datetime
from enum import StrEnum

from sqlalchemy import Column
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field, Index, SQLModel

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Role(StrEnum):
    ADMIN = "admin"
    PARTNER = "partner"
    ATTORNEY = "attorney"
    PARALEGAL = "paralegal"


class Permission(StrEnum):
    CASE_READ_ANY = "case:read:any"
    CASE_READ_ASSIGNED = "case:read:assigned"
    CASE_WRITE = "case:write"
    CASE_ASSIGN = "case:assign"
    CASE_REVIEW = "case:review"
    CASE_SUBMIT = "case:submit"


class CaseStatus(StrEnum):
    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    SUBMITTED_FOR_REVIEW = "submitted_for_review"
    UNDER_REVIEW = "under_review"
    REVISIONS_REQUESTED = "revisions_requested"
    CLOSED = "closed"


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(unique=True)
    full_name: str
    hashed_password: str
    role: Role = Field(
        sa_column=Column(
            SAEnum(
                Role,
                values_callable=lambda enum_cls: [member.value for member in enum_cls],
                name="role",
            ),
            nullable=False,
        )
    )
    is_active: bool = Field(default=True)
    must_change_password: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.now)


class Session(SQLModel, table=True):
    id: str = Field(primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    expires_at: datetime


class Case(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str
    description: str | None = None
    status: CaseStatus = Field(
        default=CaseStatus.DRAFT,
        sa_column=Column(
            SAEnum(
                CaseStatus,
                values_callable=lambda enum_cls: [member.value for member in enum_cls],
                name="casestatus",
            ),
            nullable=False,
        ),
    )
    created_at: datetime = Field(default_factory=datetime.now)


class Assignment(SQLModel, table=True):
    """Edge in the user-case bipartite graph."""

    __table_args__ = (
        Index("ix_assignment_case_id", "case_id"),
        Index("ix_assignment_user_id", "user_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    case_id: int = Field(foreign_key="case.id")
    user_id: int = Field(foreign_key="user.id")


class RolePermission(SQLModel, table=True):
    """Edge in the role-permission mapping (the permission matrix)."""

    __table_args__ = (Index("ix_role_permission_role", "role"),)

    id: int | None = Field(default=None, primary_key=True)
    role: Role
    permission: Permission


class Document(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str
    file_path: str


# ---------------------------------------------------------------------------
# LEG-51: Review round model
# ---------------------------------------------------------------------------


class Review(SQLModel, table=True):
    """A formal review round opened by a Partner on a submitted case.

    One case can have multiple review rounds (submit → revise → resubmit).
    The reviewer_id must be a Partner or Admin.
    """

    __table_args__ = (Index("ix_review_case_id", "case_id"),)

    id: int | None = Field(default=None, primary_key=True)
    case_id: int = Field(foreign_key="case.id")
    reviewer_id: int = Field(foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.now)
    # Overall verdict left by the reviewer when closing the round
    comments: str | None = None


# ---------------------------------------------------------------------------
# LEG-51: Threaded Feedback model
# ---------------------------------------------------------------------------


class Feedback(SQLModel, table=True):
    """A single node in the review feedback tree.

    Trees & recursion (CS concept):
      - parent_id = None  → root comment (Partner opens the thread)
      - parent_id = N     → reply to feedback N
      - The full thread is a tree traversed via DFS to render in order.

    Cycle guard: enforced at the service layer — a node cannot be its own
    ancestor. Orphan guard: parent_id must reference an existing Feedback row
    in the same review (FK constraint + service-layer check).
    """

    __table_args__ = (
        Index("ix_feedback_review_id", "review_id"),
        Index("ix_feedback_parent_id", "parent_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    review_id: int = Field(foreign_key="review.id")
    author_id: int = Field(foreign_key="user.id")
    content: str
    # Self-referencing FK — makes this a tree node
    parent_id: int | None = Field(default=None, foreign_key="feedback.id")
    created_at: datetime = Field(default_factory=datetime.now)
    resolved: bool = Field(default=False)
