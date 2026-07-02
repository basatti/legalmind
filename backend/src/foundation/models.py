from datetime import datetime
from enum import StrEnum

from sqlmodel import Field, SQLModel


# Enums
class Role(StrEnum):
    ADMIN = "admin"
    USER = "user"


class CaseStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    CLOSED = "closed"


# Entities
class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(unique=True)
    full_name: str
    hashed_password: str
    role: Role
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.now)


class Session(SQLModel, table=True):
    id: str = Field(primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    expires_at: datetime


class Case(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str
    description: str | None = None
    status: CaseStatus = CaseStatus.OPEN
    created_at: datetime = Field(default_factory=datetime.now)


class Assignment(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    case_id: int = Field(foreign_key="case.id")
    user_id: int = Field(foreign_key="user.id")


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
