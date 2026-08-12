import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SWRConfig } from "swr";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DocumentsSection } from "@/components/DocumentsSection";
import { ApiError } from "@/lib/api-client";
import type { Document } from "@/types/api";

/**
 * The documents list, after moving its read to SWR.
 *
 * Written with the refactor, not after it: the point of adding tests before
 * touching these components was to have something that fails if the rewrite
 * changed behaviour rather than just shape.
 *
 * Every test gets a fresh SWR cache. Without that, the second test to mount
 * the same key is served the first test's data and never calls the mock.
 */

vi.mock("@/lib/api-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api-client")>("@/lib/api-client");
  return {
    ...actual,
    apiClient: {
      documents: { list: vi.fn(), upload: vi.fn() },
    },
  };
});

const { apiClient } = await import("@/lib/api-client");
const list = vi.mocked(apiClient.documents.list);
const upload = vi.mocked(apiClient.documents.upload);

function doc(over: Partial<Document> = {}): Document {
  return {
    id: 1,
    case_id: 7,
    filename: "contract.pdf",
    uploaded_by: 2,
    uploaded_at: "2026-08-12T09:00:00",
    ...over,
  };
}

function renderSection() {
  return render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      <DocumentsSection caseId={7} />
    </SWRConfig>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("DocumentsSection", () => {
  it("lists the documents it loads", async () => {
    list.mockResolvedValue([doc(), doc({ id: 2, filename: "labor_law.pdf" })]);

    renderSection();

    expect(await screen.findByText("contract.pdf")).toBeInTheDocument();
    expect(screen.getByText("labor_law.pdf")).toBeInTheDocument();
  });

  it("says so when there are none", async () => {
    list.mockResolvedValue([]);

    renderSection();

    expect(await screen.findByText(/no documents yet/i)).toBeInTheDocument();
  });

  it("distinguishes a refusal from a failure", async () => {
    // 403 is not "something broke" — the user needs to know it is a permission
    // problem, not a retry-and-hope one.
    list.mockRejectedValue(new ApiError(403, "Forbidden"));

    renderSection();

    expect(await screen.findByText(/not authorized to view these documents/i)).toBeInTheDocument();
  });

  it("reports any other failure generically", async () => {
    list.mockRejectedValue(new ApiError(500, "boom"));

    renderSection();

    expect(await screen.findByText(/failed to load documents/i)).toBeInTheDocument();
  });

  it("shows an uploaded file without refetching the list", async () => {
    // The upload response *is* the created document, so it is appended to the
    // cache directly. A refetch here would ask the server to repeat itself.
    list.mockResolvedValue([doc()]);
    upload.mockResolvedValue(doc({ id: 9, filename: "new.pdf" }));

    const { container } = renderSection();
    await screen.findByText("contract.pdf");
    expect(list).toHaveBeenCalledTimes(1);

    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    await userEvent.upload(input, new File(["%PDF-1.4"], "new.pdf", { type: "application/pdf" }));

    expect(await screen.findByText("new.pdf")).toBeInTheDocument();
    expect(screen.getByText("contract.pdf")).toBeInTheDocument();
    expect(list).toHaveBeenCalledTimes(1);
  });

  it("shows the backend's own reason for a rejected upload", async () => {
    // "Invalid file (check type or size)" cannot say which rule was broken.
    // The backend knows, and the user is the one who has to fix it.
    //
    // The file here is a .pdf, not a .docx, and that is not incidental:
    // `userEvent.upload` honours the input's `accept`, exactly as a real file
    // picker does, so a .docx never reaches onChange at all. The reachable
    // case is a file that passes the picker and is refused by the server —
    // over the size limit, or bytes no parser can read.
    list.mockResolvedValue([]);
    upload.mockRejectedValue(
      new ApiError(400, JSON.stringify({ detail: "File exceeds the 10 MB limit" }))
    );

    const { container } = renderSection();
    await screen.findByText(/no documents yet/i);

    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    await userEvent.upload(
      input,
      new File(["x"], "huge.pdf", { type: "application/pdf" })
    );

    expect(await screen.findByText(/exceeds the 10 MB limit/i)).toBeInTheDocument();
  });

  it("falls back when a rejection body is not JSON", async () => {
    list.mockResolvedValue([]);
    upload.mockRejectedValue(new ApiError(400, "<html>proxy error</html>"));

    const { container } = renderSection();
    await screen.findByText(/no documents yet/i);

    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    await userEvent.upload(input, new File(["x"], "broken.pdf"));

    expect(await screen.findByText(/check type or size/i)).toBeInTheDocument();
  });

  it("only offers files the ingestion parser can read", async () => {
    // The picker used to offer everything, and a Word file was accepted,
    // listed, then silently failed to index.
    list.mockResolvedValue([]);

    const { container } = renderSection();
    await waitFor(() => expect(list).toHaveBeenCalled());

    const input = container.querySelector('input[type="file"]');
    expect(input).toHaveAttribute("accept", ".pdf,application/pdf");
  });
});
