import type { CaseStatus } from "@/types/api";
import type { Permission } from "@/lib/permissions";

export const ALLOWED_TRANSITIONS: Record<CaseStatus, CaseStatus[]> = {
  draft: ["in_progress"],
  in_progress: ["submitted_for_review"],
  submitted_for_review: ["under_review"],
  under_review: ["revisions_requested", "closed"],
  revisions_requested: ["in_progress"],
  closed: [],
};

export const TRANSITION_PERMISSIONS: Partial<Record<CaseStatus, Permission[]>> = {
  in_progress: ["case:edit:any", "case:edit:assigned"],
  submitted_for_review: ["case:submit_for_review"],
  under_review: ["case:review"],
  revisions_requested: ["case:review"],
  closed: ["case:close"],
};
