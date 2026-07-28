"use client";

import { useState, type FormEvent } from "react";
import { RequireAuth } from "@/components/RequireAuth";
import { CanDo } from "@/components/CanDo";
import { NotAuthorized } from "@/components/ui";
import { apiClient, ApiError } from "@/lib/api-client";
import type { Case } from "@/types/api";

export default function NewCasePage() {
  return (
    <RequireAuth>
      <CanDo
        permission="case:create"
        fallback={<NotAuthorized message="Only partners can create cases." />}
      >
        <CreateCaseForm />
      </CanDo>
    </RequireAuth>
  );
}

function CreateCaseForm() {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [createdCase, setCreatedCase] = useState<Case | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      const newCase = await apiClient.cases.create({
        title,
        description: description || null,
      });
      setCreatedCase(newCase);
      setTitle("");
      setDescription("");
    } catch (err) {
      if (err instanceof ApiError) {
        setError("Something went wrong creating the case. Please try again.");
      } else {
        setError("Something went wrong. Please try again.");
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="max-w-2xl mx-auto py-10 flex flex-col gap-8">
      <h1 className="text-xl font-semibold text-neutral-900">New Case</h1>

      <form
        onSubmit={handleSubmit}
        className="flex flex-col gap-4 bg-white border border-neutral-200 rounded-xl shadow-sm p-6"
      >
        <div className="flex flex-col gap-1">
          <label htmlFor="title" className="text-sm text-neutral-600">
            Title
          </label>
          <input
            id="title"
            type="text"
            required
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="border border-neutral-200 rounded-md px-3 py-2 text-sm text-neutral-900 focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:border-transparent"
          />
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="description" className="text-sm text-neutral-600">
            Description
          </label>
          <textarea
            id="description"
            rows={4}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="border border-neutral-200 rounded-md px-3 py-2 text-sm text-neutral-900 focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:border-transparent"
          />
        </div>

        {error && <p className="text-sm text-red-600">{error}</p>}

        <button
          type="submit"
          disabled={isSubmitting}
          className="bg-neutral-900 text-white text-sm rounded-md py-2 hover:bg-neutral-800 transition-colors disabled:opacity-50"
        >
          {isSubmitting ? "Creating…" : "Create Case"}
        </button>
      </form>

      {createdCase && (
        <div className="bg-white border border-neutral-200 rounded-xl shadow-sm p-4">
          <p className="text-sm text-neutral-900">
            Created: <span className="font-medium">{createdCase.title}</span>
          </p>
          <p className="text-xs text-neutral-500 mt-1">
            id {createdCase.id} · status {createdCase.status}
          </p>
        </div>
      )}
    </div>
  );
}
