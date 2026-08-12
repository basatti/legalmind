import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AnswerPanel } from "@/components/AnswerPanel";
import type { Citation } from "@/types/api";

/**
 * Citations are the product's whole claim: an answer a lawyer can go and check.
 *
 * This panel has been wrong twice. It rendered "Document #2" instead of a
 * filename, and it linked every source to /documents/:id — a route that does
 * not exist, so every source in a demo would have 404'd. Both were found by a
 * person clicking, which is the expensive way.
 */

const citation = (over: Partial<Citation> = {}): Citation => ({
  document_id: 1,
  document_name: "hrsd_labor_law.pdf",
  page_number: 3,
  ...over,
});

describe("AnswerPanel", () => {
  it("shows the answer text", () => {
    render(<AnswerPanel answer="Ninety days [1]." citations={[citation()]} />);

    expect(screen.getByText("Ninety days [1].")).toBeInTheDocument();
  });

  it("names the file rather than its id", () => {
    render(<AnswerPanel answer="a [1]." citations={[citation()]} />);

    expect(screen.getByText("hrsd_labor_law.pdf")).toBeInTheDocument();
    expect(screen.queryByText(/Document #/)).not.toBeInTheDocument();
  });

  it("numbers sources from 1 so they line up with the markers in the answer", () => {
    // The backend renumbers the answer's markers to match this list. If this
    // ever started at 0, an answer citing [1] would point at the second source.
    render(
      <AnswerPanel
        answer="a [1] b [2]."
        citations={[citation(), citation({ document_id: 2, document_name: "contract.pdf" })]}
      />
    );

    expect(screen.getByText("[1]")).toBeInTheDocument();
    expect(screen.getByText("[2]")).toBeInTheDocument();
    expect(screen.queryByText("[0]")).not.toBeInTheDocument();
  });

  it("shows the page, which is what makes a citation checkable", () => {
    render(<AnswerPanel answer="a [1]." citations={[citation({ page_number: 53 })]} />);

    expect(screen.getByText("Page 53")).toBeInTheDocument();
  });

  it("renders no Sources heading when there is nothing to cite", () => {
    render(<AnswerPanel answer="No answer." citations={[]} />);

    expect(screen.queryByText(/Sources/i)).not.toBeInTheDocument();
  });

  it("keeps two citations from the same document but different pages", () => {
    // They are two places to check, not a duplicate — the key includes the
    // page for exactly this reason.
    render(
      <AnswerPanel
        answer="a [1] b [2]."
        citations={[citation({ page_number: 3 }), citation({ page_number: 9 })]}
      />
    );

    expect(screen.getByText("Page 3")).toBeInTheDocument();
    expect(screen.getByText("Page 9")).toBeInTheDocument();
  });

  it("does not link a citation anywhere", () => {
    // There is no route serving a single document. A citation that promises to
    // be followable and then 404s is worse than one that does not promise.
    const { container } = render(<AnswerPanel answer="a [1]." citations={[citation()]} />);

    expect(container.querySelectorAll("a")).toHaveLength(0);
  });
});
