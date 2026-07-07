"use client";

import type { ReactNode } from "react";
import { useAuth } from "@/lib/auth";

// ---------------------------------------------------------------------------
// Logged-out shell — shown to unauthenticated users
// ---------------------------------------------------------------------------

function GuestShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-white flex flex-col">
      <header className="border-b border-neutral-100 px-6 py-4 flex items-center justify-between">
        <span className="text-sm font-semibold tracking-tight text-neutral-900">
          LegalMind
        </span>
        <span className="text-xs text-neutral-400">Sign in to continue</span>
      </header>
      <main className="flex-1 flex items-center justify-center px-6">
        {children}
      </main>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Logged-in shell — shown to authenticated users
// ---------------------------------------------------------------------------

function AuthenticatedShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();

  async function handleLogout() {
    try {
      await logout();
    } catch {
      // Best-effort — even if the backend call fails, nothing else to do here.
    }
  }

  return (
    <div className="min-h-screen bg-neutral-50 flex flex-col">
      <header className="bg-white border-b border-neutral-100 px-6 py-4 flex items-center justify-between">
        <span className="text-sm font-semibold tracking-tight text-neutral-900">
          LegalMind
        </span>
        <div className="flex items-center gap-4">
          {user && (
            <span className="text-xs text-neutral-500">{user.email}</span>
          )}
          <button
            onClick={handleLogout}
            className="text-xs text-neutral-500 hover:text-neutral-900 transition-colors"
          >
            Sign out
          </button>
        </div>
      </header>
      <div className="flex flex-1">
        <nav className="w-52 bg-white border-r border-neutral-100 px-4 py-6 flex flex-col gap-1">
          <NavItem href="/cases">Cases</NavItem>
        </nav>
        <main className="flex-1 px-8 py-6">{children}</main>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Nav item
// ---------------------------------------------------------------------------

function NavItem({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a
      href={href}
      className="text-sm text-neutral-600 hover:text-neutral-900 hover:bg-neutral-50 px-3 py-2 rounded-md transition-colors"
    >
      {children}
    </a>
  );
}

// ---------------------------------------------------------------------------
// AppShell — entry point, switches based on auth state
// ---------------------------------------------------------------------------

export function AppShell({ children }: { children: ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center">
        <span className="text-sm text-neutral-400">Loading…</span>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <GuestShell>{children}</GuestShell>;
  }

  return <AuthenticatedShell>{children}</AuthenticatedShell>;
}
