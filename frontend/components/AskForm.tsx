"use client";

import { useState } from "react";
import { ErrorState, EmptyState, Loading } from "@/components/ui";

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
          placeholder="Ask a question about this case..."
          className="flex-1 rounded-md border border-neutral-200 px-3 py-2 text-sm text-neutral-900 focus:border-neutral-400 focus:outline-none disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={isLoading || question.trim().length === 0}
          className="text-sm rounded-md bg-neutral-900 text-white px-4 py-2 hover:bg-neutral-800 disabled:opacity-50 transition-colors"
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
