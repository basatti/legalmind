"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiClient, ApiError } from "@/lib/api-client";
import { useAuth } from "@/lib/auth";
import { CanDo } from "@/components/CanDo";
import { EmptyState, ErrorState, Loading } from "@/components/ui";
import { NotAuthorized } from "@/components/ui/NotAuthorized";
import { RequireAuth } from "@/components/RequireAuth";
import { CASE_STATUS_LABELS } from "@/types/api";
import type { Case } from "@/types/api";

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------

function StatusBadge({ status }: { status: Case["status"] }) {
  const styles: Record<Case["status"], string> = {
    draft: "bg-[var(--color-slate)]/10 text-[var(--color-slate)]",
    in_progress: "bg-[var(--color-sage-bg)] text-[var(--color-sage)]",
    submitted_for_review: "bg-[var(--color-brass-light)]/40 text-[var(--color-brass-dark)]",
    under_review: "bg-[var(--color-brass-light)]/40 text-[var(--color-brass-dark)]",
    revisions_requested: "bg-[var(--color-oxblood-bg)] text-[var(--color-oxblood)]",
    closed: "bg-[var(--color-sage-bg)] text-[var(--color-sage)]",
  };

  return (
    <span className={`text-xs font-medium px-2.5 py-1 rounded-full ${styles[status]}`}>
      {CASE_STATUS_LABELS[status]}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Stat card
// ---------------------------------------------------------------------------

function StatCard({
  label,
  value,
  tone = "ink",
}: {
  label: string;
  value: number;
  tone?: "ink" | "sage" | "oxblood" | "brass";
}) {
  const toneColor: Record<string, string> = {
    ink: "text-[var(--color-ink)]",
    sage: "text-[var(--color-sage)]",
    oxblood: "text-[var(--color-oxblood)]",
    brass: "text-[var(--color-brass-dark)]",
  };

  return (
    <div className="bg-[var(--color-paper-card)] border border-[var(--color-ink)]/10 rounded-xl px-6 py-5">
      <p className="text-xs tracking-wide uppercase text-[var(--color-slate)] mb-2">
        {label}
      </p>
      <p className={`font-serif text-3xl ${toneColor[tone]}`}>{value}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Case list page
// ---------------------------------------------------------------------------

function CaseListContent() {
  const { user } = useAuth();
  const [cases, setCases] = useState<Case[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isNotAuthorized, setIsNotAuthorized] = useState(false);

  useEffect(() => {
    apiClient.cases
      .list()
      .then(setCases)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 403) {
          setIsNotAuthorized(true);
        } else {
          setError("Failed to load cases. Please try again.");
        }
      })
      .finally(() => setIsLoading(false));
  }, []);

  if (isLoading) return <Loading message="Loading cases…" />;
  if (isNotAuthorized) return <NotAuthorized />;
  if (error) return <ErrorState message={error} onRetry={() => window.location.reload()} />;

  const total = cases.length;
  const active = cases.filter((c) => c.status === "in_progress").length;
  const needsReview = cases.filter(
    (c) => c.status === "submitted_for_review" || c.status === "under_review"
  ).length;
  const pendingIntake = cases.filter((c) => c.status === "draft").length;

  return (
    <div className="min-h-screen bg-[var(--color-paper)]">
      {/* Top bar */}
      <div className="flex items-center justify-between px-8 py-5 border-b border-[var(--color-ink)]/10">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-full border border-[var(--color-brass)] flex items-center justify-center font-serif text-sm text-[var(--color-ink)]">
            L
          </div>
          <span className="font-serif text-lg text-[var(--color-ink)]">LegalMind</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs px-2.5 py-1 rounded-full bg-[var(--color-brass-light)]/40 text-[var(--color-brass-dark)] font-medium">
            {user?.role}
          </span>
          <div className="text-right leading-tight">
            <p className="text-sm text-[var(--color-ink)]">{user?.email}</p>
            <button
              onClick={() => {
                /* keep existing sign-out logic wired via useAuth if available */
              }}
              className="text-xs text-[var(--color-slate)] hover:text-[var(--color-ink)] transition-colors"
            >
              Sign out
            </button>
          </div>
          <div className="w-8 h-8 rounded-full bg-[var(--color-ink)] text-[var(--color-paper)] flex items-center justify-center text-sm font-medium">
            {user?.full_name?.[0]?.toUpperCase() ?? "A"}
          </div>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-8 py-10">
        <div className="flex items-center justify-between mb-8">
          <div>
            <p className="text-xs tracking-[0.2em] uppercase text-[var(--color-slate)] mb-1">
              Overview
            </p>
            <h1 className="font-serif text-3xl text-[var(--color-ink)]">Cases</h1>
          </div>

          <CanDo permission="case:create">
            <Link
              href="/cases/new"
              className="bg-[var(--color-ink)] text-[var(--color-paper)] text-sm font-medium rounded-md px-5 py-2.5 hover:bg-[var(--color-ink-2)] transition-colors"
            >
              + New case
            </Link>
          </CanDo>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-10">
          <StatCard label="Total cases" value={total} tone="ink" />
          <StatCard label="Active" value={active} tone="sage" />
          <StatCard label="Needs review" value={needsReview} tone="brass" />
          <StatCard label="Pending intake" value={pendingIntake} tone="oxblood" />
        </div>

        <p className="text-xs tracking-wide uppercase text-[var(--color-slate)] mb-3">
          {user?.role === "partner" || user?.role === "admin"
            ? "All cases"
            : "Your assigned cases"}
        </p>

        {cases.length === 0 ? (
          <EmptyState
            title="No cases yet"
            description="Cases assigned to you will appear here."
          />
        ) : (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {cases.map((c) => (
              <Link
                key={c.id}
                href={`/cases/${c.id}`}
                className="bg-[var(--color-paper-card)] border border-[var(--color-ink)]/10 rounded-xl px-5 py-4 flex flex-col gap-3 hover:border-[var(--color-brass)] transition-colors"
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono text-[var(--color-slate)]">
                    CASE-{String(c.id).padStart(4, "0")}
                  </span>
                  <StatusBadge status={c.status} />
                </div>
                <div>
                  <p className="font-serif text-base text-[var(--color-ink)]">
                    {c.title}
                  </p>
                  {c.description && (
                    <p className="text-xs text-[var(--color-slate)] mt-1 line-clamp-2">
                      {c.description}
                    </p>
                  )}
                </div>
                <p className="text-xs text-[var(--color-slate)]/70 pt-2 border-t border-[var(--color-ink)]/5">
                  Filed {new Date(c.created_at).toLocaleDateString()}
                </p>
              </Link>
            ))}
          </div>
        )}
      </div>

      <p className="text-xs text-center text-[var(--color-slate)]/50 py-6">
        Built by Abdullah · Rayan · Yazan
      </p>
    </div>
  );
}

export default function CasesPage() {
  return (
    <RequireAuth>
      <CaseListContent />
    </RequireAuth>
  );
}
