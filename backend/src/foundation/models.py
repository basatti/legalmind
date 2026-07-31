from datetime import datetime
from enum import StrEnum

from pgvector.sqlalchemy import Vector
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


class IngestionStatus(StrEnum):
    """Lifecycle of one ingestion job.

    PENDING → RUNNING → DONE, or back to PENDING for a retry, or FAILED once
    the attempt limit is spent. Only PENDING jobs are ever claimed, so a job
    whose worker died mid-RUNNING stays visible instead of being silently
    retried forever.
    """

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


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
    __table_args__ = (Index("ix_document_case_id", "case_id"),)
    id: int | None = Field(default=None, primary_key=True)
    case_id: int = Field(foreign_key="case.id")
    filename: str
    file_path: str
    uploaded_by: int = Field(foreign_key="user.id")
    uploaded_at: datetime = Field(default_factory=datetime.now)
    ingested_content_hash: str | None = None


# ---------------------------------------------------------------------------
# LEG-58: Document chunk model
# ---------------------------------------------------------------------------


EMBEDDING_DIMENSIONS = 1024
"""Width of every stored vector.

Fixed in the database column, so changing it means a new migration AND
re-embedding every document — vectors of different widths cannot be compared.
Chosen to match BGE-M3 / multilingual-e5-large; revisit once a model is picked.
"""


class DocumentChunk(SQLModel, table=True):
    """A searchable text chunk extracted from an uploaded document."""

    __tablename__ = "document_chunk"

    __table_args__ = (
        Index("ix_document_chunk_case_id", "case_id"),
        Index("ix_document_chunk_document_id", "document_id"),
        Index(
            "uq_document_chunk_document_sequence",
            "document_id",
            "sequence",
            unique=True,
        ),
    )

    id: int | None = Field(default=None, primary_key=True)

    case_id: int = Field(foreign_key="case.id")
    document_id: int = Field(foreign_key="document.id")

    page_number: int
    sequence: int

    text: str

    embedding: list[float] = Field(sa_column=Column(Vector(EMBEDDING_DIMENSIONS), nullable=False))

    created_at: datetime = Field(default_factory=datetime.now)


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


# ---------------------------------------------------------------------------
# LEG-59: Background ingestion queue
# ---------------------------------------------------------------------------


class IngestionJob(SQLModel, table=True):
    """One unit of background work: ingest this document.

    FIFO queue (CS concept): upload appends a row, the worker takes the oldest
    PENDING one. The index on (status, id) is what keeps that claim cheap —
    without it the worker scans every finished job to find the next pending
    one, and the queue gets slower the longer the system runs.

    attempts and last_error exist so a failure is visible rather than silent.
    A document that can never be parsed must fail loudly and step aside, not
    block everything queued behind it.
    """

    __table_args__ = (Index("ix_ingestionjob_status_id", "status", "id"),)

    id: int | None = Field(default=None, primary_key=True)
    document_id: int = Field(foreign_key="document.id")
    status: IngestionStatus = Field(
        default=IngestionStatus.PENDING,
        sa_column=Column(
            SAEnum(
                IngestionStatus,
                values_callable=lambda enum_cls: [member.value for member in enum_cls],
                name="ingestionstatus",
            ),
            nullable=False,
        ),
    )
    attempts: int = Field(default=0)
    last_error: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
