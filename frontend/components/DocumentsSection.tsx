"use client";

import { useEffect, useRef, useState } from "react";
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

export function DocumentsSection({ caseId }: { caseId: number }) {
  const [documents, setDocuments] = useState<Document[] | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function loadDocuments() {
    setIsLoading(true);
    setLoadError(null);
    apiClient.documents
      .list(caseId)
      .then(setDocuments)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 403) {
          setLoadError("You are not authorized to view these documents.");
        } else {
          setLoadError("Failed to load documents.");
        }
      })
      .finally(() => setIsLoading(false));
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- known limitation, pending a data-fetching library decision (SWR/TanStack Query) to replace manual loading/error state
    loadDocuments();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId]);

  async function handleFileSelected(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsUploading(true);
    setUploadError(null);
    try {
      const uploaded = await apiClient.documents.upload(caseId, file);
      setDocuments((prev) => (prev ? [...prev, uploaded] : [uploaded]));
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

      {!isLoading && loadError && (
        <ErrorState message={loadError} onRetry={loadDocuments} />
      )}

      {!isLoading && !loadError && documents && documents.length === 0 && (
        <EmptyState
          title="No documents yet"
          description="Upload a document to get started."
        />
      )}

      {!isLoading && !loadError && documents && documents.length > 0 && (
        <div>
          {documents.map((doc) => (
            <DocumentRow key={doc.id} document={doc} />
          ))}
        </div>
      )}
    </Section>
  );
}
