"use client";

import {
  createContext,
  useContext,
  useState,
  type ReactNode,
} from "react";
import type { User } from "@/types/api";

// ---------------------------------------------------------------------------
// Auth context shape
// ---------------------------------------------------------------------------

interface AuthContext {
  user: User | null;
  isAuthenticated: boolean;
  /** Placeholder — replace with real auth logic later */
  login: (user: User) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContext | null>(null);

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);

  function login(u: User) {
    setUser(u);
  }

  function logout() {
    setUser(null);
  }

  return (
    <AuthContext.Provider
      value={{ user, isAuthenticated: user !== null, login, logout }}
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
