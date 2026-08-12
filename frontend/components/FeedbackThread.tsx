"use client";

import { useState } from "react";
import useSWR from "swr";
import { apiClient, ApiError } from "@/lib/api-client";
import { CanDoAny } from "@/components/CanDo";
import { EmptyState, ErrorState, Loading, Section } from "@/components/ui";
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
    <div className="pl-4 border-l border-border">
      <div className="py-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-subtle">{node.author_name}</span>
          <span className="text-xs text-faint">
            {new Date(node.created_at).toLocaleString()}
          </span>
          {node.resolved && (
            <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-success-bg text-success-fg">
              Resolved
            </span>
          )}
        </div>
        <p className="text-sm text-foreground mt-1">{node.content}</p>

        <CanDoAny permissions={["case:edit:any", "case:edit:assigned"]}>
          <div className="flex items-center gap-3 mt-2">
            <button
              onClick={() => setIsReplying((v) => !v)}
              className="text-xs text-subtle hover:text-foreground transition-colors"
            >
              Reply
            </button>
            {!node.resolved && (
              <button
                onClick={markResolved}
                className="text-xs text-subtle hover:text-foreground transition-colors"
              >
                Mark resolved
              </button>
            )}
          </div>
        </CanDoAny>

        {error && <p className="text-xs text-danger-fg mt-1">{error}</p>}

        {isReplying && (
          <div className="mt-2">
            <textarea
              value={replyContent}
              onChange={(e) => setReplyContent(e.target.value)}
              className="w-full h-20 rounded-md border border-border p-2 text-sm text-foreground focus:border-border-strong focus:outline-none"
              placeholder="Write a reply..."
            />
            <button
              onClick={submitReply}
              disabled={isSubmitting || replyContent.trim().length === 0}
              className="mt-1 text-xs rounded-md bg-primary text-primary-foreground px-3 py-1.5 hover:bg-primary-hover disabled:opacity-50 transition-colors"
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
  // One SWR key for both requests rather than two, because a half-loaded thread
  // is not a state worth rendering: feedback without its review rounds has
  // nothing to hang off. Promise.all keeps them parallel, as before.
  //
  // `refreshKey` stays in the key so the parent can still force a reload after
  // it changes the case's status; `mutate` covers refreshes this component
  // causes itself.
  const { data, error, isLoading, mutate } = useSWR(
    ["review-thread", caseId, refreshKey],
    async () => {
      const [reviews, feedback] = await Promise.all([
        apiClient.reviews.list(caseId),
        apiClient.feedback.list(caseId),
      ]);
      return { reviews, feedback };
    }
  );

  const reviews: Review[] = data?.reviews ?? [];
  const feedback: Feedback[] = data?.feedback ?? [];

  // The waiting states used to render bare on the page background while every
  // neighbouring block sat in a card, which read as content that had fallen
  // out of the layout. They get the same frame as everything else.
  if (isLoading)
    return (
      <Section title="Reviews">
        <Loading message="Loading review thread…" />
      </Section>
    );
  if (error)
    return (
      <Section title="Reviews">
        <ErrorState message="Failed to load review thread." onRetry={() => mutate()} />
      </Section>
    );
  if (reviews.length === 0) {
    return (
      <Section title="Reviews">
        <EmptyState title="No reviews yet" description="This case hasn't been reviewed yet." />
      </Section>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {reviews.map((review) => {
        const roots = feedback.filter(
          (f) => f.review_id === review.id && f.parent_id === null
        );
        return (
          <Section
            key={review.id}
            title={`Review round — ${new Date(review.created_at).toLocaleDateString()}`}
          >
            {roots.map((root) => (
              <FeedbackNode
                key={root.id}
                node={root}
                allFeedback={feedback}
                caseId={caseId}
                onChanged={() => mutate()}
              />
            ))}
          </Section>
        );
      })}
    </div>
  );
}
