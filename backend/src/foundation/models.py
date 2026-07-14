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
    """Edge in the user-case bipartite graph.

    Indexes on both foreign keys avoid full table scans on the two most
    common lookups:
      - "which cases is this user assigned to?"  -> index on user_id  O(log n)
      - "which users are assigned to this case?" -> index on case_id  O(log n)
    Without indexes both queries are O(n) full scans.
    """

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


class Feedback(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    content: str
    rating: int = Field(ge=1, le=5)


class Review(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    case_id: int = Field(foreign_key="case.id")
    reviewer_id: int = Field(foreign_key="user.id")
    comments: str
