"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { apiClient, ApiError } from "@/lib/api-client";
import { CanDoAny } from "@/components/CanDo";
import { FeedbackThread } from "@/components/FeedbackThread";
import { ErrorState, Loading, Section, StatusBadge } from "@/components/ui";
import { NotAuthorized } from "@/components/ui/NotAuthorized";
import { DocumentsSection } from "@/components/DocumentsSection";
import { RagSection } from "@/components/RagSection";
import { RequireAuth } from "@/components/RequireAuth";
import { formatDate } from "@/lib/format";
import { useAuth } from "@/lib/auth";
import { usePermission } from "@/lib/usePermission";
import { hasAnyPermission, type Permission } from "@/lib/permissions";
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
      className="text-sm border border-border rounded-md px-3 py-1.5 hover:bg-surface-subtle transition-colors disabled:opacity-50"
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
      {error && <p className="text-xs text-danger-fg">{error}</p>}
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
  const { user } = useAuth();
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

  // Filter first, then decide whether the section appears. Testing the
  // unfiltered list meant "Move to" could render as a titled box with nothing
  // in it: a case awaiting review offers exactly one transition, and a
  // reviewer has that one removed because the review panel below performs it.
  //
  // Permission has to be part of the same filter, not just of the button.
  // `TransitionButton` wraps itself in `CanDoAny`, so counting transitions the
  // user cannot perform brought the empty box back for six role/status pairs -
  // a partner on an in-progress case among them, which is the demo path.
  const visibleTransitions = CASE_STATUS_TRANSITIONS[caseData.status].filter(
    (target) => {
      const required = TRANSITION_PERMISSION_MAP[target];
      const permitted =
        required.length === 0 ||
        (user !== null && hasAnyPermission(user.role, required));
      return (
        permitted &&
        !(
          caseData.status === "submitted_for_review" &&
          target === "under_review" &&
          canReview
        )
      );
    }
  );

  return (
    <div className="flex flex-col gap-4">
      {/* Back */}
      <button
        onClick={() => router.push("/cases")}
        className="text-sm text-subtle hover:text-foreground flex items-center gap-1 transition-colors self-start"
      >
        ← Cases
      </button>

      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-foreground">
            {caseData.title}
          </h1>
          <p className="text-xs text-faint mt-1">
            Created {formatDate(caseData.created_at)}
          </p>
        </div>
        {/* Edit sat in its own titled card below, which gave one link the same
            visual weight as the whole document collection. It reads as what it
            is up here: a secondary action on the case. */}
        <div className="flex items-center gap-4 shrink-0">
          <CanDoAny permissions={["case:edit:any", "case:edit:assigned"]}>
            <button
              onClick={() => router.push(`/cases/${caseData.id}/edit`)}
              className="text-sm text-subtle hover:text-foreground transition-colors"
            >
              Edit
            </button>
          </CanDoAny>
          <StatusBadge status={caseData.status} size="md" />
        </div>
      </div>

      {/* Description — the page's own content, so no card around it */}
      {caseData.description && (
        <p className="text-sm text-muted leading-relaxed">
          {caseData.description}
        </p>
      )}

      {/* Status transitions */}
      {visibleTransitions.length > 0 && (
        <Section title="Move to" variant="plain">
          <div className="flex flex-wrap gap-2">
            {visibleTransitions.map((target) => (
              <TransitionButton
                key={target}
                caseId={caseData.id!}
                targetStatus={target}
                onSuccess={setCaseData}
              />
            ))}
          </div>
        </Section>
      )}

      {caseData.status === "submitted_for_review" && canReview && (
        <Section title="Review case">
          <p className="text-sm text-muted mb-3">
            As a partner, leave the first review comment and move this case to Under Review.
          </p>
          <label className="block text-sm font-medium text-muted mb-2">
            Feedback
            <textarea
              value={reviewContent}
              onChange={(event) => setReviewContent(event.target.value)}
              className="mt-2 w-full h-28 rounded-md border border-border p-3 text-sm text-foreground focus:border-border-strong focus:outline-none"
              placeholder="Enter review feedback for the attorney..."
            />
          </label>
          {reviewError && <p className="text-xs text-danger-fg mb-3">{reviewError}</p>}
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
            className="text-sm rounded-md bg-primary text-primary-foreground px-4 py-2 hover:bg-primary-hover disabled:opacity-50 transition-colors"
          >
            {isSubmittingReview ? "Submitting…" : "Submit review"}
          </button>
        </Section>
      )}

      {/* Review thread — every round opened on this case, with replies + resolve */}
      <FeedbackThread caseId={caseData.id!} refreshKey={threadRefreshKey} />

      <DocumentsSection caseId={caseData.id!} />

      <RagSection />
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



