"use client";

import type { ReactNode } from "react";
import { useAuth } from "@/lib/auth";
import { usePermission } from "@/lib/usePermission";

// ---------------------------------------------------------------------------
// Logged-out shell
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
// Role-aware sidebar nav
// ---------------------------------------------------------------------------

function SideNav() {
  const canManageUsers = usePermission("user:manage");
  const canAssign = usePermission("case:assign");

  return (
    <nav className="w-52 bg-white border-r border-neutral-100 px-4 py-6 flex flex-col gap-1">
      {/* Everyone with case access sees Cases */}
      <NavItem href="/cases">Cases</NavItem>

      {/* Partner + Admin only — assign cases */}
      {canAssign && <NavItem href="/cases/assign">Assign Cases</NavItem>}

      {/* Admin only — user management */}
      {canManageUsers && <NavItem href="/admin/users">User Management</NavItem>}
    </nav>
  );
}

// ---------------------------------------------------------------------------
// Logged-in shell
// ---------------------------------------------------------------------------

function AuthenticatedShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();

  async function handleLogout() {
    try {
      await logout();
    } catch {
      // Best-effort
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
            <>
              <span className="text-xs text-neutral-400 capitalize">
                {user.role}
              </span>
              <span className="text-xs text-neutral-500">{user.email}</span>
            </>
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
        <SideNav />
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
// AppShell — switches based on auth state
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
