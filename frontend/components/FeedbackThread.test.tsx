import { render, screen } from "@testing-library/react";
import { SWRConfig } from "swr";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FeedbackThread } from "@/components/FeedbackThread";
import type { Feedback, Review } from "@/types/api";

/**
 * The review thread, after moving its read to SWR.
 *
 * Two behaviours here have each been wrong once. It rendered "User #29" where
 * a name belongs, and its two requests were fired separately — a half-loaded
 * thread has feedback with no review round to hang off, which is not a state
 * worth rendering.
 *
 * `CanDoAny` is mocked to render its children: the permission gate has its own
 * tests in lib/permissions.test.ts, and wiring an auth context through here
 * would test the provider rather than the thread.
 */

vi.mock("@/lib/api-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api-client")>("@/lib/api-client");
  return {
    ...actual,
    apiClient: {
      reviews: { list: vi.fn() },
      feedback: { list: vi.fn(), reply: vi.fn(), resolve: vi.fn() },
    },
  };
});

vi.mock("@/components/CanDo", () => ({
  CanDo: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  CanDoAny: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

const { apiClient } = await import("@/lib/api-client");
const listReviews = vi.mocked(apiClient.reviews.list);
const listFeedback = vi.mocked(apiClient.feedback.list);

const review: Review = {
  id: 1,
  case_id: 7,
  reviewer_id: 29,
  created_at: "2026-08-12T09:00:00",
  comments: null,
};

function comment(over: Partial<Feedback> = {}): Feedback {
  return {
    id: 1,
    review_id: 1,
    author_id: 29,
    author_name: "Perry Partner",
    content: "Please clarify the probation clause.",
    parent_id: null,
    created_at: "2026-08-12T09:00:00",
    resolved: false,
    ...over,
  };
}

function renderThread() {
  return render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      <FeedbackThread caseId={7} refreshKey={0} />
    </SWRConfig>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("FeedbackThread", () => {
  it("names the author instead of showing an id", async () => {
    listReviews.mockResolvedValue([review]);
    listFeedback.mockResolvedValue([comment()]);

    renderThread();

    expect(await screen.findByText("Perry Partner")).toBeInTheDocument();
    expect(screen.queryByText(/User #/)).not.toBeInTheDocument();
  });

  it("nests a reply under the comment it answers", async () => {
    listReviews.mockResolvedValue([review]);
    listFeedback.mockResolvedValue([
      comment(),
      comment({ id: 2, parent_id: 1, author_id: 30, author_name: "Annie Attorney", content: "Clarified." }),
    ]);

    renderThread();

    expect(await screen.findByText("Perry Partner")).toBeInTheDocument();
    expect(screen.getByText("Annie Attorney")).toBeInTheDocument();
    expect(screen.getByText("Clarified.")).toBeInTheDocument();
  });

  it("loads both requests together", async () => {
    // One SWR key, not two: feedback without its review rounds has nothing to
    // render against, so a half-loaded thread is not a state worth showing.
    listReviews.mockResolvedValue([review]);
    listFeedback.mockResolvedValue([comment()]);

    renderThread();
    await screen.findByText("Perry Partner");

    expect(listReviews).toHaveBeenCalledTimes(1);
    expect(listFeedback).toHaveBeenCalledTimes(1);
  });

  it("says so when the case has never been reviewed", async () => {
    listReviews.mockResolvedValue([]);
    listFeedback.mockResolvedValue([]);

    renderThread();

    expect(await screen.findByText(/no reviews yet/i)).toBeInTheDocument();
  });

  it("reports a failure without losing the frame", async () => {
    listReviews.mockRejectedValue(new Error("network"));
    listFeedback.mockResolvedValue([]);

    renderThread();

    expect(await screen.findByText(/failed to load review thread/i)).toBeInTheDocument();
  });

  it("marks a resolved comment as resolved", async () => {
    listReviews.mockResolvedValue([review]);
    listFeedback.mockResolvedValue([comment({ resolved: true })]);

    renderThread();

    expect(await screen.findByText(/resolved/i)).toBeInTheDocument();
  });
});
