// ---------------------------------------------------------------------------
// Enums — mirror backend Role and CaseStatus StrEnums exactly
// ---------------------------------------------------------------------------

export type Role = "admin" | "partner" | "attorney" | "paralegal";

export type CaseStatus =
  | "draft"
  | "in_progress"
  | "submitted_for_review"
  | "under_review"
  | "revisions_requested"
  | "closed";

// ---------------------------------------------------------------------------
// Entities
// ---------------------------------------------------------------------------

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  must_change_password: boolean;
}

export interface Case {
  id: number | null;
  title: string;
  description: string | null;
  status: CaseStatus;
  created_at: string;
}

export interface Assignment {
  id: number | null;
  case_id: number;
  user_id: number;
}

export interface Document {
  id: number | null;
  case_id: number;
  filename: string;
  uploaded_by: number;
  uploaded_at: string;
}

export interface Review {
  id: number;
  case_id: number;
  reviewer_id: number;
  created_at: string;
  comments: string | null;
}

export interface Feedback {
  id: number;
  review_id: number;
  author_id: number;
  /** Display name of whoever wrote it. The id is what we key on; this is what
   * a reader sees — "User #29" told a lawyer nothing about who is asking them
   * to revise a case. Falls back to "Unknown user" server-side when the author
   * no longer has a row. */
  author_name: string;
  content: string;
  parent_id: number | null;
  created_at: string;
  resolved: boolean;
}

// ---------------------------------------------------------------------------
// Request shapes
// ---------------------------------------------------------------------------

export interface LoginRequest {
  email: string;
  password: string;
}

export interface UserCreateRequest {
  email: string;
  full_name: string;
  temporary_password: string;
  role: Role;
}

export interface CaseCreateRequest {
  title: string;
  description?: string | null;
}

export interface CaseUpdateRequest {
  title?: string | null;
  description?: string | null;
}

export interface CaseTransitionRequest {
  target_status: CaseStatus;
}

export interface ReviewCreateRequest {
  content: string;
}

export interface FeedbackReplyRequest {
  parent_id: number;
  content: string;
}

export interface ChangePasswordRequest {
  current_password: string;
  new_password: string;
}

// ---------------------------------------------------------------------------
// Response shapes
// ---------------------------------------------------------------------------

export interface RootResponse {
  message: string;
}

export interface HealthResponse {
  status: string;
}

export interface LoginResponse {
  message: string;
  must_change_password: boolean;
}

export interface MessageResponse {
  message: string;
}

// ---------------------------------------------------------------------------
// State machine — mirrors backend FSM (CASE_STATUS_TRANSITIONS)
// ---------------------------------------------------------------------------

export const CASE_STATUS_TRANSITIONS: Record<CaseStatus, CaseStatus[]> = {
  draft: ["in_progress"],
  in_progress: ["submitted_for_review"],
  submitted_for_review: ["under_review"],
  under_review: ["revisions_requested", "closed"],
  revisions_requested: ["in_progress"],
  closed: [],
};

export const CASE_STATUS_LABELS: Record<CaseStatus, string> = {
  draft: "Draft",
  in_progress: "In Progress",
  submitted_for_review: "Submitted for Review",
  under_review: "Under Review",
  revisions_requested: "Revisions Requested",
  closed: "Closed",
};

// ---------------------------------------------------------------------------
// RAG — ask a question, scoped to the user's authorized cases
//
// Mirrors foundation/schemas.py (QueryAskResponse / CitationResponse). A
// citation carries the document's name as well as its id, so the UI can show a
// lawyer the filename they recognise rather than a database key. It does not
// carry chunk_text.
// ---------------------------------------------------------------------------

export interface AskRequest {
  question: string;
}

export interface Citation {
  document_id: number;
  document_name: string;
  page_number: number;
}

export interface AskResponse {
  answer: string | null;
  citations: Citation[];
}
