"use client";

import { useEffect, useState, type FormEvent } from "react";
import { RequireAuth } from "@/components/RequireAuth";
import { CanDo } from "@/components/CanDo";
import { EmptyState, ErrorState, Loading, NotAuthorized } from "@/components/ui";
import { apiClient, ApiError } from "@/lib/api-client";
import { CASE_STATUS_LABELS } from "@/types/api";
import type { Case, User } from "@/types/api";

export default function AssignCasePage() {
  return (
    <RequireAuth>
      <CanDo
        permission="case:assign"
        fallback={<NotAuthorized message="Only partners can assign cases." />}
      >
        <AssignCaseForm />
      </CanDo>
    </RequireAuth>
  );
}

function AssignCaseForm() {
  const [cases, setCases] = useState<Case[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [caseId, setCaseId] = useState("");
  const [userId, setUserId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([apiClient.cases.list(), apiClient.users.list()])
      .then(([caseData, userData]) => {
        setCases(caseData);
        setUsers(userData.filter((u) => u.role === "attorney" || u.role === "paralegal"));
      })
      .catch(() => setLoadError("Failed to load cases or users. Please try again."))
      .finally(() => setIsLoading(false));
  }, []);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccessMessage(null);
    setIsSubmitting(true);

    try {
      await apiClient.cases.assign(Number(caseId), Number(userId));
      const assignedCase = cases.find((c) => c.id === Number(caseId));
      const assignedUser = users.find((u) => u.id === Number(userId));
      setSuccessMessage(
        `Assigned ${assignedUser?.full_name ?? "user"} to "${assignedCase?.title ?? "case"}".`
      );
      setCaseId("");
      setUserId("");
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError("That user is already assigned to this case.");
      } else if (err instanceof ApiError && err.status === 400) {
        setError("That user can't be assigned to a case.");
      } else {
        setError("Something went wrong. Please try again.");
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  if (isLoading) return <Loading message="Loading cases…" />;
  if (loadError)
    return <ErrorState message={loadError} onRetry={() => window.location.reload()} />;

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold text-foreground">Assign Case</h1>

      {cases.length === 0 || users.length === 0 ? (
        <EmptyState
          title={cases.length === 0 ? "No cases yet" : "Nobody to assign"}
          description={
            cases.length === 0
              ? "Create a case before assigning it to someone."
              : "Only attorneys and paralegals can be assigned to a case."
          }
        />
      ) : (
        <form
          onSubmit={handleSubmit}
          className="flex flex-col gap-4 bg-surface border border-border rounded-xl shadow-sm p-6 max-w-xl"
        >
          <div className="flex flex-col gap-1">
            <label htmlFor="case" className="text-sm text-muted">
              Case
            </label>
            <select
              id="case"
              required
              value={caseId}
              onChange={(e) => setCaseId(e.target.value)}
              className="border border-border rounded-md px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-foreground focus:border-transparent"
            >
              <option value="" disabled>
                Select a case
              </option>
              {cases.map((c) => (
                // dir="auto" so a title takes its direction from its own first
                // strong character. Without it an Arabic title followed by a
                // Latin "(Draft)" gets reordered by the bidi algorithm and the
                // status appears to jump to the wrong end of the line.
                <option key={c.id} value={c.id ?? ""} dir="auto">
                  {c.title} ({CASE_STATUS_LABELS[c.status]})
                </option>
              ))}
            </select>
          </div>

          <div className="flex flex-col gap-1">
            <label htmlFor="user" className="text-sm text-muted">
              Assign to
            </label>
            <select
              id="user"
              required
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              className="border border-border rounded-md px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-foreground focus:border-transparent"
            >
              <option value="" disabled>
                Select a person
              </option>
              {users.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.full_name} ({u.role})
                </option>
              ))}
            </select>
          </div>

          {error && <p className="text-sm text-danger-fg">{error}</p>}
          {successMessage && <p className="text-sm text-success-fg">{successMessage}</p>}

          <button
            type="submit"
            disabled={isSubmitting}
            className="bg-primary text-primary-foreground text-sm rounded-md py-2 hover:bg-primary-hover transition-colors disabled:opacity-50"
          >
            {isSubmitting ? "Assigning…" : "Assign"}
          </button>
        </form>
      )}
    </div>
  );
}
