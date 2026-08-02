"use client";

import { useEffect, type ReactNode } from "react";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth";
import { usePermission } from "@/lib/usePermission";

function Signature() {
  return (
    <div className="fixed bottom-3 right-4 z-40 pointer-events-none">
      <span className="font-mono text-[11px] tracking-wide text-slate/50">
        Built by Abdullah · Rayan · Yazan
      </span>
    </div>
  );
}

function GuestShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-paper flex flex-col">
      <header className="border-b border-ink/10 px-6 py-4 flex items-center justify-between bg-paper-card">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-full border border-brass-light flex items-center justify-center font-serif text-sm text-brass-dark">
            L
          </div>
          <span className="font-serif text-base tracking-tight text-ink">
            LegalMind
          </span>
        </div>
        <span className="text-xs text-slate">Sign in to continue</span>
      </header>
      <main className="flex-1 flex items-center justify-center px-6">
        {children}
      </main>
      <Signature />
    </div>
  );
}

function SideNav() {
  const canManageUsers = usePermission("user:manage");
  const canAssign = usePermission("case:assign");

  return (
    <nav className="w-64 bg-ink flex flex-col shrink-0">
      <div className="flex items-center gap-3 px-6 py-6 border-b border-white/10">
        <div className="w-8 h-8 rounded-full border border-brass-light flex items-center justify-center font-serif text-base text-brass-light">
          L
        </div>
        <span className="font-serif text-lg text-paper">LegalMind</span>
      </div>

      <div className="flex-1 py-6 space-y-1">
        <NavItem href="/cases">Cases</NavItem>
        {canAssign && <NavItem href="/cases/assign">Assign cases</NavItem>}
        {canManageUsers && (
          <NavItem href="/admin/users">User management</NavItem>
        )}
      </div>

      <div className="px-6 py-5 border-t border-white/10">
        <p className="font-mono text-[11px] text-paper/30 tracking-wide">
          DOCKET SYSTEM · EST. 2026
        </p>
      </div>
    </nav>
  );
}

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
    <div className="min-h-screen bg-paper flex">
      <SideNav />

      <div className="flex-1 flex flex-col">
        <header className="bg-paper-card border-b border-ink/5 px-8 py-4 flex items-center justify-between">
          <div />
          <div className="flex items-center gap-4">
            {user && (
              <>
                <span className="text-xs font-medium text-brass-dark bg-brass/10 px-3 py-1.5 rounded-full capitalize">
                  {user.role}
                </span>
                <div className="text-right leading-tight">
                  <p className="text-sm font-medium text-ink">
                    {user.email}
                  </p>
                  <button
                    onClick={handleLogout}
                    className="text-xs text-slate hover:text-oxblood transition-colors"
                  >
                    Sign out
                  </button>
                </div>
                <div className="w-9 h-9 rounded-full bg-ink text-paper flex items-center justify-center font-serif text-sm">
                  {user.email.charAt(0).toUpperCase()}
                </div>
              </>
            )}
          </div>
        </header>

        <main className="flex-1 px-8 py-6 bg-paper">{children}</main>
      </div>

      <Signature />
    </div>
  );
}

function NavItem({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link
      href={href}
      className="flex items-center gap-3 px-6 py-3 text-paper hover:text-brass-light hover:bg-white/5 text-sm font-medium transition-colors whitespace-nowrap"
    >
      <span className="w-4 h-4 border border-brass-light/50 rounded-sm shrink-0" />
      {children}
    </Link>
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
      <div className="min-h-screen bg-paper flex items-center justify-center">
        <span className="text-sm text-slate font-mono">Loading…</span>
      </div>
    );
  }

  if (pathname === "/login") {
    return <>{children}</>;
  }

  if (!isAuthenticated) {
    return <GuestShell>{children}</GuestShell>;
  }

  return <AuthenticatedShell>{children}</AuthenticatedShell>;
}
