"use client";

import { useState } from "react";
import { apiClient, ApiError } from "@/lib/api-client";
import { CanDoAny } from "@/components/CanDo";
import { AskForm } from "@/components/AskForm";
import { AnswerPanel } from "@/components/AnswerPanel";
import type { Citation } from "@/types/api";

function RagSectionContent() {
  const [answer, setAnswer] = useState<string | null>(null);
  const [citations, setCitations] = useState<Citation[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasAsked, setHasAsked] = useState(false);

  async function handleAsk(question: string) {
    setIsLoading(true);
    setError(null);
    setHasAsked(true);
    try {
      const result = await apiClient.rag.ask({ question });
      setAnswer(result.answer);
      setCitations(result.citations);
    } catch (err) {
      setAnswer(null);
      setCitations([]);
      if (err instanceof ApiError && err.status === 503) {
        setError("The answering service is temporarily unavailable. Try again shortly.");
      } else {
        setError("Failed to get an answer. Please try again.");
      }
    } finally {
      setIsLoading(false);
    }
  }

  const notFound = hasAsked && !isLoading && !error && answer === null;

  return (
    <div className="flex flex-col gap-4">
      <p className="text-xs font-medium text-neutral-500 uppercase tracking-wide">
        Ask a question
      </p>
      <AskForm
        onSubmit={handleAsk}
        isLoading={isLoading}
        error={error}
        notFound={notFound}
      />
      {!isLoading && !error && answer && (
        <AnswerPanel answer={answer} citations={citations} />
      )}
    </div>
  );
}

export function RagSection() {
  return (
    <CanDoAny permissions={["case:read:any", "case:read:assigned"]}>
      <RagSectionContent />
    </CanDoAny>
  );
}
