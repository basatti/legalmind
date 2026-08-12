"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useParams, useRouter } from "next/navigation";
import { apiClient, ApiError } from "@/lib/api-client";
import { CanDoAny } from "@/components/CanDo";
import { RequireAuth } from "@/components/RequireAuth";
import { ErrorState, Loading, NotAuthorized } from "@/components/ui";

export default function EditCasePage() {
  const params = useParams();
  const caseId = Number(params.id);

  return (
    <RequireAuth>
      {/* Mirrors the gate on the Edit button that leads here. It is not the
          real protection: every role holds at least `case:edit:assigned`, so
          this passes for everyone. The backend's 403 — handled on both the
          load and the save below — is what stops an attorney editing a case
          they are not assigned to. */}
      <CanDoAny
        permissions={["case:edit:any", "case:edit:assigned"]}
        fallback={<NotAuthorized message="You cannot edit cases." />}
      >
        <EditCaseForm caseId={caseId} />
      </CanDoAny>
    </RequireAuth>
  );
}

function EditCaseForm({ caseId }: { caseId: number }) {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isNotAuthorized, setIsNotAuthorized] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  // An edit form has to read before it can write: the inputs start as the
  // case's current values, so there is nothing to render until this lands.
  useEffect(() => {
    apiClient.cases
      .get(caseId)
      .then((data) => {
        setTitle(data.title);
        setDescription(data.description ?? "");
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 403) {
          setIsNotAuthorized(true);
        } else if (err instanceof ApiError && err.status === 404) {
          setLoadError("Case not found.");
        } else {
          setLoadError("Failed to load case.");
        }
      })
      .finally(() => setIsLoading(false));
  }, [caseId]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();

    // `required` on the input stops an empty box but not a box holding only
    // spaces, which the backend rejects with a 422. Trimming here means the
    // stored title matches what the user sees they typed.
    const trimmedTitle = title.trim();
    if (!trimmedTitle) {
      setError("Title must not be empty.");
      return;
    }

    setError(null);
    setIsSaving(true);

    try {
      await apiClient.cases.update(caseId, {
        title: trimmedTitle,
        // Sent as-is rather than `description || null`. A PATCH reads null as
        // "leave this field alone", so clearing the box and sending null would
        // silently keep the old text — the case page would still show the
        // description the user just deleted. An empty string is the only way
        // to say "make it empty".
        description,
      });
      router.push(`/cases/${caseId}`);
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setError("You are not assigned to this case.");
      } else if (err instanceof ApiError && err.status === 404) {
        setError("Case not found.");
      } else if (err instanceof ApiError && err.status === 422) {
        setError("Title must not be empty.");
      } else {
        setError("Something went wrong saving the case. Please try again.");
      }
      setIsSaving(false);
    }
  }

  if (isLoading) return <Loading message="Loading case…" />;
  if (isNotAuthorized) return <NotAuthorized />;
  if (loadError) return <ErrorState message={loadError} />;

  return (
    <div className="flex flex-col gap-8">
      <h1 className="text-xl font-semibold text-foreground">Edit Case</h1>

      <form
        onSubmit={handleSubmit}
        className="flex flex-col gap-4 bg-surface border border-border rounded-xl shadow-sm p-6 max-w-xl"
      >
        <div className="flex flex-col gap-1">
          <label htmlFor="title" className="text-sm text-muted">
            Title
          </label>
          <input
            id="title"
            type="text"
            required
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="border border-border rounded-md px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-foreground focus:border-transparent"
          />
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="description" className="text-sm text-muted">
            Description
          </label>
          <textarea
            id="description"
            rows={4}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="border border-border rounded-md px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-foreground focus:border-transparent"
          />
        </div>

        {error && <p className="text-sm text-danger-fg">{error}</p>}

        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={isSaving}
            className="bg-primary text-primary-foreground text-sm rounded-md px-4 py-2 hover:bg-primary-hover transition-colors disabled:opacity-50"
          >
            {isSaving ? "Saving…" : "Save changes"}
          </button>
          <button
            type="button"
            onClick={() => router.push(`/cases/${caseId}`)}
            className="text-sm text-subtle hover:text-foreground transition-colors"
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
