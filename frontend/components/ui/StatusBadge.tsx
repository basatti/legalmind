import { CASE_STATUS_LABELS, type CaseStatus } from "@/types/api";

// One copy of the status palette. This lived in both the case list and the
// case detail page, which meant a colour change had to be made twice and the
// two drifted apart in size and shape.
const STATUS_COLORS: Record<CaseStatus, string> = {
  draft: "bg-surface-muted text-muted",
  in_progress: "bg-info-bg text-info-fg",
  submitted_for_review: "bg-warn-bg text-warn-fg",
  under_review: "bg-review-bg text-review-fg",
  revisions_requested: "bg-revision-bg text-revision-fg",
  closed: "bg-success-bg text-success-fg",
};

// The two call sites genuinely want different weights - a row badge should not
// shout as loudly as the one beside the page title - so size is a prop rather
// than a reason to keep two components.
const SIZES = {
  sm: "text-xs px-2 py-0.5",
  md: "text-sm px-3 py-1",
} as const;

export function StatusBadge({
  status,
  size = "sm",
}: {
  status: CaseStatus;
  size?: keyof typeof SIZES;
}) {
  return (
    <span className={`font-medium rounded-full ${SIZES[size]} ${STATUS_COLORS[status]}`}>
      {CASE_STATUS_LABELS[status]}
    </span>
  );
}
