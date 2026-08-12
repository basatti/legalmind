"use client";

import { useRef, useState } from "react";
import useSWR from "swr";
import { apiClient, ApiError } from "@/lib/api-client";
import { EmptyState, ErrorState, Loading, Section } from "@/components/ui";
import { formatDate } from "@/lib/format";
import type { Document } from "@/types/api";

// ---------------------------------------------------------------------------
// Single document row
// ---------------------------------------------------------------------------

function DocumentRow({ document }: { document: Document }) {
  return (
    <div className="flex items-center justify-between py-3 border-b border-border-subtle last:border-0">
      <div className="flex flex-col">
        <span className="text-sm font-medium text-foreground">
          {document.filename}
        </span>
        <span className="text-xs text-subtle">
          Uploaded {formatDate(document.uploaded_at)}
        </span>
      </div>
    </div>
  );
}

/** The backend's own message for a rejected upload, or `fallback` if there
 *  isn't one. `ApiError.message` carries the raw response body, so the useful
 *  half — "File type '.docx' is not allowed. Accepted: .pdf" — has to be dug
 *  out of the JSON. Worth digging: the generic wording cannot say which of the
 *  two rules the file broke, and the user is the one who has to fix it. */
function rejectionReason(error: ApiError, fallback: string): string {
  try {
    const body: unknown = JSON.parse(error.message);
    if (
      typeof body === "object" &&
      body !== null &&
      "detail" in body &&
      typeof body.detail === "string"
    ) {
      return body.detail;
    }
  } catch {
    // Not JSON — a proxy error page, say. The fallback is the honest answer.
  }
  return fallback;
}

// ---------------------------------------------------------------------------
// Documents section — upload + list
// ---------------------------------------------------------------------------

/** Why the read is SWR and the write is not.
 *
 * Loading used to be `useEffect` + three `useState`s, which needed two
 * `eslint-disable` lines: React's `set-state-in-effect` rule objects to the
 * pattern itself, not to this implementation of it. `useSWR` owns the fetch,
 * the loading flag and the error, so the suppressions are gone rather than
 * silenced — and a second mount of the same case serves from cache instead of
 * refetching.
 *
 * Uploading stays hand-written. It is a one-shot action with its own progress
 * and its own error vocabulary, and the only shared state it touches is the
 * list, which it updates through `mutate`. */
export function DocumentsSection({ caseId }: { caseId: number }) {
  const {
    data: documents,
    error: loadError,
    isLoading,
    mutate,
  } = useSWR<Document[], unknown>(["documents", caseId], () =>
    apiClient.documents.list(caseId)
  );

  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadErrorMessage =
    loadError instanceof ApiError && loadError.status === 403
      ? "You are not authorized to view these documents."
      : loadError
        ? "Failed to load documents."
        : null;

  async function handleFileSelected(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsUploading(true);
    setUploadError(null);
    try {
      const uploaded = await apiClient.documents.upload(caseId, file);
      // The response *is* the created document, so appending it is accurate and
      // instant. `revalidate: false` keeps that a cache write rather than a
      // round trip — refetching here would ask the server to repeat what it
      // just told us.
      await mutate((current) => [...(current ?? []), uploaded], {
        revalidate: false,
      });
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 400) {
          setUploadError(
            rejectionReason(err, "Invalid file (check type or size).")
          );
        } else if (err.status === 403) {
          setUploadError("You are not authorized to upload documents.");
        } else {
          setUploadError("Upload failed.");
        }
      } else {
        setUploadError("Upload failed.");
      }
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  return (
    <Section
      title="Documents"
      action={
        <div className="flex flex-col items-end gap-1">
          <label
            className={`text-sm border border-border rounded-md px-3 py-1.5 hover:bg-surface-subtle transition-colors cursor-pointer ${
              isUploading ? "opacity-50 pointer-events-none" : ""
            }`}
          >
            {isUploading ? "Uploading…" : "Upload document"}
            {/* Only what the ingestion parser can actually read. Without this
                the picker offered every file on the machine, and a Word file
                was accepted, listed, and then silently failed to index. Widen
                it when a parser for another type is registered, not before. */}
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,application/pdf"
              className="hidden"
              onChange={handleFileSelected}
              disabled={isUploading}
            />
          </label>
          {uploadError && (
            <p className="text-xs text-danger-fg">{uploadError}</p>
          )}
        </div>
      }
    >
      {isLoading && <Loading message="Loading documents…" />}

      {!isLoading && loadErrorMessage && (
        <ErrorState message={loadErrorMessage} onRetry={() => mutate()} />
      )}

      {!isLoading && !loadErrorMessage && documents && documents.length === 0 && (
        <EmptyState
          title="No documents yet"
          description="Upload a document to get started."
        />
      )}

      {!isLoading && !loadErrorMessage && documents && documents.length > 0 && (
        <div>
          {documents.map((doc) => (
            <DocumentRow key={doc.id} document={doc} />
          ))}
        </div>
      )}
    </Section>
  );
}
