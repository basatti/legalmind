from enum import Enum
from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional
from datetime import datetime

# Enums
class Role(str, Enum):
    ADMIN = "admin"
    USER = "user"

class CaseStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    CLOSED = "closed"

# Entities
class User(BaseModel):
    id: int
    username: str
    email: EmailStr
    role: Role

class Case(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    status: CaseStatus = CaseStatus.OPEN
    created_at: datetime = Field(default_factory=datetime.now)

class Assignment(BaseModel):
    id: int
    case_id: int
    user_id: int

class Document(BaseModel):
    id: int
    title: str
    file_path: str

class Feedback(BaseModel):
    id: int
    content: str
    rating: int = Field(ge=1, le=5)

class Review(BaseModel):
    id: int
    case_id: int
    reviewer_id: int
    comments: str
    