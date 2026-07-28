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
  const colors: Record<Case["status"], string> = {
    draft: "bg-neutral-100 text-neutral-600",
    in_progress: "bg-blue-50 text-blue-700",
    submitted_for_review: "bg-yellow-50 text-yellow-700",
    under_review: "bg-purple-50 text-purple-700",
    revisions_requested: "bg-orange-50 text-orange-700",
    closed: "bg-green-50 text-green-700",
  };

  return (
    <span
      className={`text-xs font-medium px-2 py-0.5 rounded-full ${colors[status]}`}
    >
      {CASE_STATUS_LABELS[status]}
    </span>
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

  return (
    <div className="max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-neutral-900">Cases</h1>
          <p className="text-sm text-neutral-500 mt-0.5">
            {user?.role === "partner" || user?.role === "admin"
              ? "All cases"
              : "Your assigned cases"}
          </p>
        </div>

        {/* Create case — Partner/Admin only */}
        <CanDo permission="case:create">
          <Link
            href="/cases/new"
            className="bg-neutral-900 text-white text-sm rounded-md px-4 py-2 hover:bg-neutral-800 transition-colors"
          >
            New case
          </Link>
        </CanDo>
      </div>

      {cases.length === 0 ? (
        <EmptyState
          title="No cases yet"
          description="Cases assigned to you will appear here."
        />
      ) : (
        <div className="flex flex-col gap-2">
          {cases.map((c) => (
            <Link
              key={c.id}
              href={`/cases/${c.id}`}
              className="bg-white border border-neutral-200 rounded-lg px-5 py-4 flex items-center justify-between hover:border-neutral-400 transition-colors"
            >
              <div>
                <p className="text-sm font-medium text-neutral-900">
                  {c.title}
                </p>
                {c.description && (
                  <p className="text-xs text-neutral-500 mt-0.5 line-clamp-1">
                    {c.description}
                  </p>
                )}
              </div>
              <div className="flex items-center gap-3 shrink-0 ml-4">
                <StatusBadge status={c.status} />
                <span className="text-neutral-300 text-sm">→</span>
              </div>
            </Link>
          ))}
        </div>
      )}
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
