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
    resolved: bool


class ReviewResponse(BaseModel):
    id: int
    case_id: int
    reviewer_id: int
    created_at: datetime
    comments: str | None


# ---------------------------------------
# LEG-XX: Document upload & listing
# ---------------------------------------
class DocumentOut(BaseModel):
    id: int
    case_id: int
    filename: str
    uploaded_by: int
    uploaded_at: datetime


# ---------------------------------------------------------------------------
# LEG-61: Scoped query endpoint
# ---------------------------------------------------------------------------


class QueryAskRequest(BaseModel):
    question: str

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Question must not be empty")
        return value


class CitationResponse(BaseModel):
    """Where one part of an answer came from, in terms a person can go and check."""

    document_id: int
    document_name: str
    page_number: int


class QueryAskResponse(BaseModel):
    """answer is None whenever there is nothing to say: the user has no
    authorized cases, retrieval found nothing, or the model's reply could not be
    trusted. All three look identical to the caller on purpose — never a guess,
    and never an HTTP error for any of them.

    citations is empty when answer is None, and otherwise lists every place the
    answer draws on, so the reader can verify it against the source rather than
    taking it on faith.

    LEG-75 locks this shape against exposing the graph's internals. `GraphState`
    carries `route` and `reasoning` (LEG-74), and neither belongs here:

    - Reasoning is unvalidated. `AnswerService` discards a reply that cites a
      passage it wasn't given, cites nothing, or reports NOT_FOUND — that check
      is why `answer` can be put in front of a lawyer. Nothing checks the
      reason node's intermediate working. Rendered beside a validated answer,
      a discarded sub-conclusion reads as a finding.
    - It leaks facts about the case. How many passes a question took and which
      sub-questions found nothing are things the caller may not be entitled to
      — the same reason LEG-78's iteration cap degrades to "no answer" instead
      of reporting that it was hit.
    - Langfuse already owns this. LEG-83/84 give one trace per run, and LEG-88
      is the walkthrough for debugging a wrong answer from it. Shipping
      reasoning through the API builds that twice, the second time worse.

    Still open, deliberately: enriching CitationResponse with the document
    filename, so the UI stops rendering "Document #2" (LEG-69, decided in
    LEG-79). That is additive — an extra field breaks no existing caller — and
    is not what this lock forbids.
    """

    answer: str | None = None
    citations: list[CitationResponse] = []
