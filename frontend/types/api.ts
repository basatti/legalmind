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
  title: string;
  file_path: string;
}

export interface Feedback {
  id: number | null;
  content: string;
  rating: number;
}

export interface Review {
  id: number | null;
  case_id: number;
  reviewer_id: number;
  comments: string;
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
