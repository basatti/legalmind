// ---------------------------------------------------------------------------
// Enums — mirror backend Role and CaseStatus StrEnums exactly
// ---------------------------------------------------------------------------

export type Role = "admin" | "user";

export type CaseStatus = "open" | "in_progress" | "closed";

// ---------------------------------------------------------------------------
// Entities — mirror backend SQLModel table models exactly
// ---------------------------------------------------------------------------

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
}

export interface Case {
  id: number | null;
  title: string;
  description: string | null;
  status: CaseStatus;
  created_at: string; // ISO 8601 datetime string from FastAPI
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
  rating: number; // 1–5
}

export interface Review {
  id: number | null;
  case_id: number;
  reviewer_id: number;
  comments: string;
}

// ---------------------------------------------------------------------------
// API response shapes — root and health endpoints
// ---------------------------------------------------------------------------

export interface RootResponse {
  message: string;
}

export interface HealthResponse {
  status: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface MessageResponse {
  message: string;
}
