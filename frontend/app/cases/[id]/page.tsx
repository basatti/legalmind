"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { apiClient, ApiError } from "@/lib/api-client";
import { CanDoAny } from "@/components/CanDo";
import { FeedbackThread } from "@/components/FeedbackThread";
import { ErrorState, Loading } from "@/components/ui";
import { NotAuthorized } from "@/components/ui/NotAuthorized";
import { RequireAuth } from "@/components/RequireAuth";
import { usePermission } from "@/lib/usePermission";
import type { Permission } from "@/lib/permissions";
import {
  CASE_STATUS_LABELS,
  CASE_STATUS_TRANSITIONS,
  type Case,
  type CaseStatus,
  type ReviewCreateRequest,
} from "@/types/api";

// ---------------------------------------------------------------------------
// Which permissions are needed to trigger each transition
// Mirrors backend TRANSITION_PERMISSIONS in case_router.py exactly
// ---------------------------------------------------------------------------

const TRANSITION_PERMISSION_MAP: Record<CaseStatus, Permission[]> = {
  draft: [],
  in_progress: ["case:edit:any", "case:edit:assigned"],
  submitted_for_review: ["case:submit_for_review"],
  under_review: ["case:review"],
  revisions_requested: ["case:review"],
  closed: ["case:close"],
};

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------

function StatusBadge({ status }: { status: CaseStatus }) {
  const colors: Record<CaseStatus, string> = {
    draft: "bg-neutral-100 text-neutral-600",
    in_progress: "bg-blue-50 text-blue-700",
    submitted_for_review: "bg-yellow-50 text-yellow-700",
    under_review: "bg-purple-50 text-purple-700",
    revisions_requested: "bg-orange-50 text-orange-700",
    closed: "bg-green-50 text-green-700",
  };

  return (
    <span className={`text-sm font-medium px-3 py-1 rounded-full ${colors[status]}`}>
      {CASE_STATUS_LABELS[status]}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Transition button
// ---------------------------------------------------------------------------

function TransitionButton({
  caseId,
  targetStatus,
  onSuccess,
}: {
  caseId: number;
  targetStatus: CaseStatus;
  onSuccess: (updated: Case) => void;
}) {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const permissions = TRANSITION_PERMISSION_MAP[targetStatus];

  async function handleTransition() {
    setIsLoading(true);
    setError(null);
    try {
      const updated = await apiClient.cases.transition(caseId, {
        target_status: targetStatus,
      });
      onSuccess(updated);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.status === 403 ? "Not permitted" : "Transition failed");
      }
    } finally {
      setIsLoading(false);
    }
  }

  const button = (
    <button
      onClick={handleTransition}
      disabled={isLoading}
      className="text-sm border border-neutral-200 rounded-md px-3 py-1.5 hover:bg-neutral-50 transition-colors disabled:opacity-50"
    >
      {isLoading ? "…" : `→ ${CASE_STATUS_LABELS[targetStatus]}`}
    </button>
  );

  return (
    <div className="flex flex-col gap-1">
      {permissions.length > 0 ? (
        <CanDoAny permissions={permissions}>
          {button}
        </CanDoAny>
      ) : (
        button
      )}
      {error && <p className="text-xs text-red-500">{error}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Case detail content
// ---------------------------------------------------------------------------

function CaseDetailContent({ caseId }: { caseId: number }) {
  const router = useRouter();
  const [caseData, setCaseData] = useState<Case | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isNotAuthorized, setIsNotAuthorized] = useState(false);
  const canReview = usePermission("case:review");
  const [reviewContent, setReviewContent] = useState("");
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [isSubmittingReview, setIsSubmittingReview] = useState(false);
  const [threadRefreshKey, setThreadRefreshKey] = useState(0);

  useEffect(() => {
    apiClient.cases
      .get(caseId)
      .then(setCaseData)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 403) {
          setIsNotAuthorized(true);
        } else if (err instanceof ApiError && err.status === 404) {
          setError("Case not found.");
        } else {
          setError("Failed to load case.");
        }
      })
      .finally(() => setIsLoading(false));
  }, [caseId]);

  if (isLoading) return <Loading message="Loading case…" />;
  if (isNotAuthorized) return <NotAuthorized />;
  if (error || !caseData) return <ErrorState message={error ?? "Case not found."} />;

  const allowedTransitions = CASE_STATUS_TRANSITIONS[caseData.status];

  return (
    <div className="max-w-2xl mx-auto">
      {/* Back */}
      <button
        onClick={() => router.push("/cases")}
        className="text-sm text-neutral-500 hover:text-neutral-900 mb-6 flex items-center gap-1 transition-colors"
      >
        ← Cases
      </button>

      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-neutral-900">
            {caseData.title}
          </h1>
          <p className="text-xs text-neutral-400 mt-1">
            Created {new Date(caseData.created_at).toLocaleDateString()}
          </p>
        </div>
        <StatusBadge status={caseData.status} />
      </div>

      {/* Description */}
      {caseData.description && (
        <div className="bg-white border border-neutral-200 rounded-lg px-5 py-4 mb-4">
          <p className="text-sm text-neutral-600 leading-relaxed">
            {caseData.description}
          </p>
        </div>
      )}

      {/* Status transitions */}
      {allowedTransitions.length > 0 && (
        <div className="bg-white border border-neutral-200 rounded-lg px-5 py-4 mb-4">
          <p className="text-xs font-medium text-neutral-500 uppercase tracking-wide mb-3">
            Move to
          </p>
          <div className="flex flex-wrap gap-2">
            {allowedTransitions
        .filter((target) =>
          caseData.status === "submitted_for_review" &&
          target === "under_review" &&
          canReview
            ? false
            : true
        )
        .map((target) => (
          <TransitionButton
            key={target}
            caseId={caseData.id!}
            targetStatus={target}
            onSuccess={setCaseData}
          />
        ))}
          </div>
        </div>
      )}

      {caseData.status === "submitted_for_review" && canReview && (
        <div className="bg-white border border-neutral-200 rounded-lg px-5 py-4 mb-4">
          <p className="text-xs font-medium text-neutral-500 uppercase tracking-wide mb-3">
            Review case
          </p>
          <p className="text-sm text-neutral-600 mb-3">
            As a partner, leave the first review comment and move this case to Under Review.
          </p>
          <label className="block text-sm font-medium text-neutral-700 mb-2">
            Feedback
            <textarea
              value={reviewContent}
              onChange={(event) => setReviewContent(event.target.value)}
              className="mt-2 w-full h-28 rounded-md border border-neutral-200 p-3 text-sm text-neutral-900 focus:border-neutral-400 focus:outline-none"
              placeholder="Enter review feedback for the attorney..."
            />
          </label>
          {reviewError && <p className="text-xs text-red-500 mb-3">{reviewError}</p>}
          <button
            onClick={async () => {
              setReviewError(null);
              setIsSubmittingReview(true);
              try {
                if (!caseData.id) {
                  throw new Error("Case ID is missing.");
                }
                const payload: ReviewCreateRequest = { content: reviewContent };
                await apiClient.cases.review(caseData.id, payload);
                setReviewContent("");
                setThreadRefreshKey((key) => key + 1);
                setCaseData((current) =>
                  current ? { ...current, status: "under_review" } : current
                );
              } catch (err) {
                if (err instanceof ApiError) {
                  setReviewError(err.status === 403 ? "Not permitted" : "Failed to submit review.");
                } else {
                  setReviewError("Failed to submit review.");
                }
              } finally {
                setIsSubmittingReview(false);
              }
            }}
            disabled={isSubmittingReview || reviewContent.trim().length === 0}
            className="text-sm rounded-md bg-neutral-900 text-white px-4 py-2 hover:bg-neutral-800 disabled:opacity-50 transition-colors"
          >
            {isSubmittingReview ? "Submitting…" : "Submit review"}
          </button>
        </div>
      )}

      {/* Review thread — every round opened on this case, with replies + resolve */}
      <div className="mb-4">
        <FeedbackThread caseId={caseData.id!} refreshKey={threadRefreshKey} />
      </div>

      {/* Edit — assigned users only */}
      <CanDoAny permissions={["case:edit:any", "case:edit:assigned"]}>
        <div className="bg-white border border-neutral-200 rounded-lg px-5 py-4">
          <p className="text-xs font-medium text-neutral-500 uppercase tracking-wide mb-3">
            Actions
          </p>
          <button
            onClick={() => router.push(`/cases/${caseData.id}/edit`)}
            className="text-sm text-neutral-600 hover:text-neutral-900 transition-colors"
          >
            Edit case details
          </button>
        </div>
      </CanDoAny>
    </div>
  );
}

export default function CaseDetailPage() {
  const params = useParams();
  const caseId = Number(params.id);

  return (
    <RequireAuth>
      <CaseDetailContent caseId={caseId} />
    </RequireAuth>
  );
}
