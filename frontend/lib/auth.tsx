"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { apiClient } from "@/lib/api-client";
import type { User } from "@/types/api";

// ---------------------------------------------------------------------------
// Auth context shape
// ---------------------------------------------------------------------------

interface AuthContext {
  user: User | null;
  isAuthenticated: boolean;
  /** True while checking for an existing session on first load */
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  /** Re-fetch the current user — call after anything that changes their info server-side */
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContext | null>(null);

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // On first mount, ask the backend if we already have a valid session cookie.
  useEffect(() => {
    apiClient.auth
      .me()
      .then((currentUser) => setUser(currentUser))
      .catch(() => setUser(null)) // 401 means "not logged in" — not an error we care about here
      .finally(() => setIsLoading(false));
  }, []);

  async function refreshUser() {
    const currentUser = await apiClient.auth.me();
    setUser(currentUser);
  }

  async function login(email: string, password: string) {
    await apiClient.auth.login({ email, password }); // throws ApiError on wrong credentials
    await refreshUser();
  }

  async function logout() {
    await apiClient.auth.logout();
    setUser(null);
  }

  return (
    <AuthContext.Provider
      value={{ user, isAuthenticated: user !== null, isLoading, login, logout, refreshUser }}
    >
      {children}
    </AuthContext.Provider>
  );
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useAuth(): AuthContext {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
