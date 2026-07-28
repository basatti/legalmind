"use client";

import { useEffect, useState, type FormEvent } from "react";
import { RequireAuth } from "@/components/RequireAuth";
import { CanDo } from "@/components/CanDo";
import { NotAuthorized } from "@/components/ui";
import { apiClient, ApiError } from "@/lib/api-client";
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

  if (isLoading) return <p className="text-sm text-neutral-500 max-w-md mx-auto py-10">Loading…</p>;
  if (loadError) return <p className="text-sm text-red-600 max-w-md mx-auto py-10">{loadError}</p>;

  return (
    <div className="max-w-md mx-auto py-10 flex flex-col gap-6">
      <h1 className="text-xl font-semibold text-neutral-900">Assign Case</h1>

      {cases.length === 0 || users.length === 0 ? (
        <p className="text-sm text-neutral-500">
          {cases.length === 0
            ? "No cases exist yet."
            : "No attorneys or paralegals to assign."}
        </p>
      ) : (
        <form
          onSubmit={handleSubmit}
          className="flex flex-col gap-4 bg-white border border-neutral-200 rounded-xl shadow-sm p-6"
        >
          <div className="flex flex-col gap-1">
            <label htmlFor="case" className="text-sm text-neutral-600">
              Case
            </label>
            <select
              id="case"
              required
              value={caseId}
              onChange={(e) => setCaseId(e.target.value)}
              className="border border-neutral-200 rounded-md px-3 py-2 text-sm text-neutral-900 focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:border-transparent"
            >
              <option value="" disabled>
                Select a case
              </option>
              {cases.map((c) => (
                <option key={c.id} value={c.id ?? ""}>
                  {c.title} ({c.status})
                </option>
              ))}
            </select>
          </div>

          <div className="flex flex-col gap-1">
            <label htmlFor="user" className="text-sm text-neutral-600">
              Assign to
            </label>
            <select
              id="user"
              required
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              className="border border-neutral-200 rounded-md px-3 py-2 text-sm text-neutral-900 focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:border-transparent"
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

          {error && <p className="text-sm text-red-600">{error}</p>}
          {successMessage && <p className="text-sm text-green-600">{successMessage}</p>}

          <button
            type="submit"
            disabled={isSubmitting}
            className="bg-neutral-900 text-white text-sm rounded-md py-2 hover:bg-neutral-800 transition-colors disabled:opacity-50"
          >
            {isSubmitting ? "Assigning…" : "Assign"}
          </button>
        </form>
      )}
    </div>
  );
}
