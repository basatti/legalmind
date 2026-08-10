"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiClient, ApiError } from "@/lib/api-client";
import { useAuth } from "@/lib/auth";
import { CanDo } from "@/components/CanDo";
import { EmptyState, ErrorState, Loading, StatusBadge } from "@/components/ui";
import { NotAuthorized } from "@/components/ui/NotAuthorized";
import { RequireAuth } from "@/components/RequireAuth";
import type { Case } from "@/types/api";

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
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-foreground">Cases</h1>
          <p className="text-sm text-subtle mt-0.5">
            {user?.role === "partner" || user?.role === "admin"
              ? "All cases"
              : "Your assigned cases"}
          </p>
        </div>

        {/* Create case — Partner/Admin only */}
        <CanDo permission="case:create">
          <Link
            href="/cases/new"
            className="bg-primary text-primary-foreground text-sm rounded-md px-4 py-2 hover:bg-primary-hover transition-colors"
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
              className="bg-surface border border-border rounded-lg px-5 py-4 flex items-center justify-between hover:border-border-strong transition-colors"
            >
              <div>
                <p className="text-sm font-medium text-foreground">
                  {c.title}
                </p>
                {c.description && (
                  <p className="text-xs text-subtle mt-0.5 line-clamp-1">
                    {c.description}
                  </p>
                )}
              </div>
              <div className="flex items-center gap-3 shrink-0 ml-4">
                <StatusBadge status={c.status} />
                <span className="text-faint text-sm">→</span>
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
