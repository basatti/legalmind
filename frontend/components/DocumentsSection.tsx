"use client";

import { useEffect, useRef, useState } from "react";
import { apiClient, ApiError } from "@/lib/api-client";
import { EmptyState, ErrorState, Loading } from "@/components/ui";
import type { Document } from "@/types/api";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDate(isoString: string): string {
  return new Date(isoString).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

// ---------------------------------------------------------------------------
// Single document row
// ---------------------------------------------------------------------------

function DocumentRow({ document }: { document: Document }) {
  return (
    <div className="flex items-center justify-between py-3 border-b border-neutral-100 last:border-0">
      <div className="flex flex-col">
        <span className="text-sm font-medium text-neutral-800">
          {document.filename}
        </span>
        <span className="text-xs text-neutral-500">
          Uploaded {formatDate(document.uploaded_at)}
        </span>
      </div>
    </div>
  );
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
          setUploadError("Invalid file (check type or size).");
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
    <div className="mt-8">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-medium text-neutral-800">Documents</h2>

        <div className="flex flex-col items-end gap-1">
          <label
            className={`text-sm border border-neutral-200 rounded-md px-3 py-1.5 hover:bg-neutral-50 transition-colors cursor-pointer ${
              isUploading ? "opacity-50 pointer-events-none" : ""
            }`}
          >
            {isUploading ? "Uploading…" : "Upload document"}
            <input
              ref={fileInputRef}
              type="file"
              className="hidden"
              onChange={handleFileSelected}
              disabled={isUploading}
            />
          </label>
          {uploadError && (
            <p className="text-xs text-red-500">{uploadError}</p>
          )}
        </div>
      </div>

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
    </div>
  );
}
