"use client";

import { useEffect, useState } from "react";
import { apiClient, ApiError } from "@/lib/api-client";
import { CanDoAny } from "@/components/CanDo";
import { EmptyState, ErrorState, Loading } from "@/components/ui";
import type { Feedback, Review } from "@/types/api";

// ---------------------------------------------------------------------------
// A single feedback node + its replies (recursive)
// ---------------------------------------------------------------------------

function FeedbackNode({
  node,
  allFeedback,
  caseId,
  onChanged,
}: {
  node: Feedback;
  allFeedback: Feedback[];
  caseId: number;
  onChanged: () => void;
}) {
  const [isReplying, setIsReplying] = useState(false);
  const [replyContent, setReplyContent] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const children = allFeedback.filter((f) => f.parent_id === node.id);

  async function submitReply() {
    setError(null);
    setIsSubmitting(true);
    try {
      await apiClient.feedback.reply(caseId, {
        parent_id: node.id,
        content: replyContent,
      });
      setReplyContent("");
      setIsReplying(false);
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError && err.status === 403 ? "Not permitted" : "Failed to reply.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function markResolved() {
    setError(null);
    try {
      await apiClient.feedback.resolve(caseId, node.id);
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError && err.status === 403 ? "Not permitted" : "Failed to resolve.");
    }
  }

  return (
    <div className="pl-4 border-l border-neutral-200">
      <div className="py-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-neutral-500">User #{node.author_id}</span>
          <span className="text-xs text-neutral-400">
            {new Date(node.created_at).toLocaleString()}
          </span>
          {node.resolved && (
            <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-green-50 text-green-700">
              Resolved
            </span>
          )}
        </div>
        <p className="text-sm text-neutral-800 mt-1">{node.content}</p>

        <CanDoAny permissions={["case:edit:any", "case:edit:assigned"]}>
          <div className="flex items-center gap-3 mt-2">
            <button
              onClick={() => setIsReplying((v) => !v)}
              className="text-xs text-neutral-500 hover:text-neutral-900 transition-colors"
            >
              Reply
            </button>
            {!node.resolved && (
              <button
                onClick={markResolved}
                className="text-xs text-neutral-500 hover:text-neutral-900 transition-colors"
              >
                Mark resolved
              </button>
            )}
          </div>
        </CanDoAny>

        {error && <p className="text-xs text-red-500 mt-1">{error}</p>}

        {isReplying && (
          <div className="mt-2">
            <textarea
              value={replyContent}
              onChange={(e) => setReplyContent(e.target.value)}
              className="w-full h-20 rounded-md border border-neutral-200 p-2 text-sm text-neutral-900 focus:border-neutral-400 focus:outline-none"
              placeholder="Write a reply..."
            />
            <button
              onClick={submitReply}
              disabled={isSubmitting || replyContent.trim().length === 0}
              className="mt-1 text-xs rounded-md bg-neutral-900 text-white px-3 py-1.5 hover:bg-neutral-800 disabled:opacity-50 transition-colors"
            >
              {isSubmitting ? "Sending…" : "Send reply"}
            </button>
          </div>
        )}
      </div>

      {children.map((child) => (
        <FeedbackNode
          key={child.id}
          node={child}
          allFeedback={allFeedback}
          caseId={caseId}
          onChanged={onChanged}
        />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// The full thread: every review round on this case + its feedback tree
// ---------------------------------------------------------------------------

export function FeedbackThread({
  caseId,
  refreshKey,
}: {
  caseId: number;
  refreshKey: number;
}) {
  const [reviews, setReviews] = useState<Review[]>([]);
  const [feedback, setFeedback] = useState<Feedback[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  function load() {
    setIsLoading(true);
    setError(null);
    Promise.all([apiClient.reviews.list(caseId), apiClient.feedback.list(caseId)])
      .then(([reviewList, feedbackList]) => {
        setReviews(reviewList);
        setFeedback(feedbackList);
      })
      .catch(() => setError("Failed to load review thread."))
      .finally(() => setIsLoading(false));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId, refreshKey]);

  if (isLoading) return <Loading message="Loading review thread…" />;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (reviews.length === 0) {
    return <EmptyState title="No reviews yet" description="This case hasn't been reviewed yet." />;
  }

  return (
    <div className="flex flex-col gap-6">
      {reviews.map((review) => {
        const roots = feedback.filter(
          (f) => f.review_id === review.id && f.parent_id === null
        );
        return (
          <div key={review.id} className="bg-white border border-neutral-200 rounded-lg px-5 py-4">
            <p className="text-xs font-medium text-neutral-500 uppercase tracking-wide mb-3">
              Review round — {new Date(review.created_at).toLocaleDateString()}
            </p>
            {roots.map((root) => (
              <FeedbackNode
                key={root.id}
                node={root}
                allFeedback={feedback}
                caseId={caseId}
                onChanged={load}
              />
            ))}
          </div>
        );
      })}
    </div>
  );
}
