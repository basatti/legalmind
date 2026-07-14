import type {
  Case,
  HealthResponse,
  LoginRequest,
  LoginResponse,
  MessageResponse,
  RootResponse,
  User,
  UserCreateRequest,
} from "@/types/api";

// ---------------------------------------------------------------------------
// Base config
// ---------------------------------------------------------------------------

const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ---------------------------------------------------------------------------
// Core fetch wrapper — typed, no any
// ---------------------------------------------------------------------------

async function apiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${BASE_URL}${path}`;

  const res = await fetch(url, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
    ...options,
  });

  if (!res.ok) {
    const text = await res.text();
    throw new ApiError(res.status, text);
  }

  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Error type
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// ---------------------------------------------------------------------------
// Endpoint methods
// ---------------------------------------------------------------------------

export const apiClient = {
  /** GET / — health/welcome check */
  root(): Promise<RootResponse> {
    return apiFetch<RootResponse>("/");
  },

  /** GET /health */
  health(): Promise<HealthResponse> {
    return apiFetch<HealthResponse>("/health");
  },

  cases: {
    /** GET /cases/ — list all cases */
    list(): Promise<Case[]> {
      return apiFetch<Case[]>("/cases/");
    },

    /** POST /cases/ — create a new case */
    create(data: Omit<Case, "id" | "created_at">): Promise<Case> {
      return apiFetch<Case>("/cases/", {
        method: "POST",
        body: JSON.stringify(data),
      });
    },
  },

  auth: {
    /** POST /auth/login — verify credentials, server sets session cookie */
    login(data: LoginRequest): Promise<LoginResponse> {
      return apiFetch<LoginResponse>("/auth/login", {
        method: "POST",
        body: JSON.stringify(data),
      });
    },

    /** POST /auth/logout — invalidate session, clears cookie */
    logout(): Promise<MessageResponse> {
      return apiFetch<MessageResponse>("/auth/logout", {
        method: "POST",
      });
    },

    /** GET /auth/me — returns the current user, or throws 401 if not logged in */
    me(): Promise<User> {
      return apiFetch<User>("/auth/me");
    },
  },

  users: {
    /** GET /users/ — list all users, admin-only */
    list(): Promise<User[]> {
      return apiFetch<User[]>("/users/");
    },

    /** POST /users/ — create a new user, admin-only */
    create(data: UserCreateRequest): Promise<User> {
      return apiFetch<User>("/users/", {
        method: "POST",
        body: JSON.stringify(data),
      });
    },
  },
} as const;
