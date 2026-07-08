"""Pydantic schemas for request/response validation."""

from datetime import datetime

from pydantic import BaseModel, EmailStr, field_validator

from foundation.models import CaseStatus


class UserRegisterRequest(BaseModel):
    email: EmailStr
    full_name: str
    password: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not any(char.isdigit() for char in value):
            raise ValueError("Password must contain at least one digit")
        if not any(char.isalpha() for char in value):
            raise ValueError("Password must contain at least one letter")
        return value


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    is_active: bool


# ---------------------------------------------------------------------------
# LEG-22: Login
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class MessageResponse(BaseModel):
    message: str


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
