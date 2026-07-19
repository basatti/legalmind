"""Pydantic schemas for request/response validation."""

from datetime import datetime

from pydantic import BaseModel, EmailStr, field_validator

from foundation.models import CaseStatus, Role


def _validate_password_rules(value: str) -> str:
    if len(value) < 8:
        raise ValueError("Password must be at least 8 characters long")
    if not any(char.isdigit() for char in value):
        raise ValueError("Password must contain at least one digit")
    if not any(char.isalpha() for char in value):
        raise ValueError("Password must contain at least one letter")
    return value


# ---------------------------------------------------------------------------
# LEG-21: Admin-only user creation (replaces public registration)
# ---------------------------------------------------------------------------


class UserCreateRequest(BaseModel):
    email: EmailStr
    full_name: str
    temporary_password: str
    role: Role

    @field_validator("temporary_password")
    @classmethod
    def validate_temporary_password(cls, value: str) -> str:
        return _validate_password_rules(value)


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: Role
    is_active: bool
    must_change_password: bool


# ---------------------------------------------------------------------------
# LEG-22: Login
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    message: str
    must_change_password: bool


class MessageResponse(BaseModel):
    message: str


# ---------------------------------------------------------------------------
# LEG-21: Change password (first login, or any time after)
# ---------------------------------------------------------------------------


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        return _validate_password_rules(value)


# ---------------------------------------------------------------------------
# LEG-36: Case CRUD
# ---------------------------------------------------------------------------


class CaseCreateRequest(BaseModel):
    title: str
    description: str | None = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Title must not be empty")
        return value


class CaseUpdateRequest(BaseModel):
    title: str | None = None
    description: str | None = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Title must not be empty")
        return value


class CaseResponse(BaseModel):
    id: int
    title: str
    description: str | None
    status: str
    created_at: datetime


# ---------------------------------------------------------------------------
# LEG-XX: Case state transitions
# ---------------------------------------------------------------------------


class CaseTransitionRequest(BaseModel):
    target_status: CaseStatus


# ---------------------------------------------------------------------------
# LEG-40: Case assignment
# ---------------------------------------------------------------------------


class AssignmentCreateRequest(BaseModel):
    user_id: int


class AssignmentResponse(BaseModel):
    id: int
    case_id: int
    user_id: int


# ---------------------------------------------------------------------------
# LEG-52: Review + threaded feedback
# ---------------------------------------------------------------------------


class ReviewCreateRequest(BaseModel):
    content: str

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Feedback content must not be empty")
        return value


class FeedbackReplyRequest(BaseModel):
    parent_id: int
    content: str

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Feedback content must not be empty")
        return value


class FeedbackResponse(BaseModel):
    id: int
    review_id: int
    author_id: int
    content: str
    parent_id: int | None
    created_at: datetime
