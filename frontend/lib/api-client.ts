import type {
  Assignment,
  Case,
  CaseCreateRequest,
  CaseTransitionRequest,
  CaseUpdateRequest,
  Document,
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

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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

async function apiUpload<T>(path: string, formData: FormData): Promise<T> {
  const url = `${BASE_URL}${path}`;

  const res = await fetch(url, {
    method: "POST",
    credentials: "include",
    body: formData,
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
  root(): Promise<RootResponse> {
    return apiFetch<RootResponse>("/");
  },

  health(): Promise<HealthResponse> {
    return apiFetch<HealthResponse>("/health");
  },

  cases: {
    /** GET /cases/ — list cases (scoped by assignment on the backend) */
    list(): Promise<Case[]> {
      return apiFetch<Case[]>("/cases/");
    },

    /** GET /cases/:id — get a single case */
    get(id: number): Promise<Case> {
      return apiFetch<Case>(`/cases/${id}`);
    },

    /** POST /cases/ — create a new case (Partner/Admin only) */
    create(data: CaseCreateRequest): Promise<Case> {
      return apiFetch<Case>("/cases/", {
        method: "POST",
        body: JSON.stringify(data),
      });
    },

    /** PATCH /cases/:id — update title/description */
    update(id: number, data: CaseUpdateRequest): Promise<Case> {
      return apiFetch<Case>(`/cases/${id}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      });
    },

    /** POST /cases/:id/transition — advance the state machine */
    transition(id: number, data: CaseTransitionRequest): Promise<Case> {
      return apiFetch<Case>(`/cases/${id}/transition`, {
        method: "POST",
        body: JSON.stringify(data),
      });
    },

    /** POST /cases/{id}/assign — assign a user to a case */
    assign(id: number, userId: number): Promise<Assignment> {
      return apiFetch<Assignment>(`/cases/${id}/assign`, {
        method: "POST",
        body: JSON.stringify({ user_id: userId }),
      });
    },
  },

  documents: {
    /** GET /cases/:caseId/documents/ — list documents for a case */
    list(caseId: number): Promise<Document[]> {
      return apiFetch<Document[]>(`/cases/${caseId}/documents/`);
    },

    /** POST /cases/:caseId/documents/ — upload a document */
    upload(caseId: number, file: File): Promise<Document> {
      const formData = new FormData();
      formData.append("file", file);
      return apiUpload<Document>(`/cases/${caseId}/documents/`, formData);
    },
  },

  auth: {
    login(data: LoginRequest): Promise<LoginResponse> {
      return apiFetch<LoginResponse>("/auth/login", {
        method: "POST",
        body: JSON.stringify(data),
      });
    },

    logout(): Promise<MessageResponse> {
      return apiFetch<MessageResponse>("/auth/logout", {
        method: "POST",
      });
    },

    me(): Promise<User> {
      return apiFetch<User>("/auth/me");
    },
  },

  users: {
    list(): Promise<User[]> {
      return apiFetch<User[]>("/users/");
    },

    create(data: UserCreateRequest): Promise<User> {
      return apiFetch<User>("/users/", {
        method: "POST",
        body: JSON.stringify(data),
      });
    },
  },
} as const;
