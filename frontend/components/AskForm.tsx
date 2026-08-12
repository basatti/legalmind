"use client";

import { useState } from "react";
import { ErrorState, EmptyState, Loading } from "@/components/ui";

/** Deliberately not "about this case".
 *
 * POST /query/ask is scoped to every case the user is authorised for, not the
 * one on screen — see the note in lib/api-client.ts. So an answer can correctly
 * cite a different case, and the old wording made that look like a scope leak
 * to anyone watching. The box promises what the endpoint actually does. */
const QUESTION_PLACEHOLDER = "Ask a question about your cases...";

interface AskFormProps {
  /** Called with the trimmed question text on submit. No API calls happen
   * inside this component — the parent owns fetching. */
  onSubmit: (question: string) => void;
  isLoading: boolean;
  /** Set by the parent when the last submit failed. */
  error?: string | null;
  /** Set by the parent when the last question resolved with no answer
   * (answer === null from the backend), as distinct from an error. */
  notFound?: boolean;
}

export function AskForm({
  onSubmit,
  isLoading,
  error = null,
  notFound = false,
}: AskFormProps) {
  const [question, setQuestion] = useState("");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || isLoading) return;
    onSubmit(trimmed);
  }

  return (
    <div className="flex flex-col gap-4">
      <form onSubmit={handleSubmit} className="flex items-start gap-3">
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          disabled={isLoading}
          placeholder={QUESTION_PLACEHOLDER}
          className="flex-1 rounded-md border border-border px-3 py-2 text-sm text-foreground focus:border-border-strong focus:outline-none disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={isLoading || question.trim().length === 0}
          className="text-sm rounded-md bg-primary text-primary-foreground px-4 py-2 hover:bg-primary-hover disabled:opacity-50 transition-colors"
        >
          {isLoading ? "Asking…" : "Ask"}
        </button>
      </form>

      {isLoading && <Loading message="Finding an answer…" />}

      {!isLoading && error && (
        <ErrorState message={error} onRetry={() => onSubmit(question.trim())} />
      )}

      {!isLoading && !error && notFound && (
        <EmptyState
          title="No answer found"
          description="Nothing in your authorized cases answers this question."
        />
      )}
    </div>
  );
}
