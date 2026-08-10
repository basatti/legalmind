"use client";

import { useEffect, type ReactNode } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { usePermission } from "@/lib/usePermission";

// ---------------------------------------------------------------------------
// Logged-out shell
// ---------------------------------------------------------------------------

function GuestShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-surface flex flex-col">
      <header className="border-b border-border-subtle px-6 py-4 flex items-center justify-between">
        <span className="text-sm font-semibold tracking-tight text-foreground">
          LegalMind
        </span>
        <a
          href="/login"
          className="bg-primary text-primary-foreground text-xs rounded-md px-3 py-1.5 hover:bg-primary-hover transition-colors"
        >
          Sign in
        </a>
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
    <nav className="w-52 bg-surface border-r border-border-subtle px-4 py-6 flex flex-col gap-1">
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
    <div className="min-h-screen bg-surface-subtle flex flex-col">
      <header className="bg-surface border-b border-border-subtle px-6 py-4 flex items-center justify-between">
        <span className="text-sm font-semibold tracking-tight text-foreground">
          LegalMind
        </span>
        <div className="flex items-center gap-4">
          {user && (
            <>
              <span className="text-xs text-faint capitalize">
                {user.role}
              </span>
              <span className="text-xs text-subtle">{user.email}</span>
            </>
          )}
          <button
            onClick={handleLogout}
            className="text-xs text-subtle hover:text-foreground transition-colors"
          >
            Sign out
          </button>
        </div>
      </header>
      <div className="flex flex-1">
        <SideNav />
        {/* The shell owns the content column so every page lines up in the
            same place. Pages that set their own max-width used to disagree -
            896px on the case list, 448px on Assign - so the frame jumped on
            each navigation. Pages style their content; the frame is not
            theirs to pick. */}
        <main className="flex-1 px-8 py-8">
          <div className="max-w-4xl mx-auto w-full">{children}</div>
        </main>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Nav item
// ---------------------------------------------------------------------------

function NavItem({ href, children }: { href: string; children: ReactNode }) {
  const pathname = usePathname();

  // "/cases" must not light up while you are on "/cases/assign", so the parent
  // match is deliberately exact. Only the case detail route (/cases/123) rolls
  // up into Cases, since it has no nav entry of its own.
  const isActive =
    pathname === href || (href === "/cases" && /^\/cases\/\d+$/.test(pathname));

  return (
    <a
      href={href}
      aria-current={isActive ? "page" : undefined}
      className={`text-sm px-3 py-2 rounded-md transition-colors ${
        isActive
          ? "bg-surface-muted text-foreground font-medium"
          : "text-muted hover:text-foreground hover:bg-surface-subtle"
      }`}
    >
      {children}
    </a>
  );
}

// ---------------------------------------------------------------------------
// AppShell — switches based on auth state, and gates on forced password change
// ---------------------------------------------------------------------------

export function AppShell({ children }: { children: ReactNode }) {
  const { user, isAuthenticated, isLoading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  const mustChangePassword = user?.must_change_password ?? false;

  // The one shared checkpoint every page passes through: if a logged-in
  // user still has a temporary password, send them to /change-password
  // no matter which page they were trying to reach.
  useEffect(() => {
    if (!isLoading && isAuthenticated && mustChangePassword && pathname !== "/change-password") {
      router.push("/change-password");
    }
  }, [isLoading, isAuthenticated, mustChangePassword, pathname, router]);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-surface flex items-center justify-center">
        <span className="text-sm text-faint">Loading…</span>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <GuestShell>{children}</GuestShell>;
  }

  return <AuthenticatedShell>{children}</AuthenticatedShell>;
}
