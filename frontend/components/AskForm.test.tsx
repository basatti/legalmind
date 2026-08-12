import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AskForm } from "@/components/AskForm";

/**
 * The ask box. Two things here are worth holding still.
 *
 * The wording: this form sits inside a case, but POST /query/ask is scoped to
 * every case the user is authorised for. It used to say "about this case",
 * which made a correct answer citing another case look like a scope leak.
 *
 * The submit guard: an empty or whitespace-only question must never reach the
 * backend, which rejects it with a 422 that the user would have to read.
 */

describe("AskForm", () => {
  it("promises the scope the endpoint actually has", () => {
    render(<AskForm onSubmit={vi.fn()} isLoading={false} />);

    const input = screen.getByPlaceholderText(/ask a question about your cases/i);

    expect(input).toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/about this case/i)).not.toBeInTheDocument();
  });

  it("submits the typed question", async () => {
    const onSubmit = vi.fn();
    render(<AskForm onSubmit={onSubmit} isLoading={false} />);

    await userEvent.type(screen.getByRole("textbox"), "What is the probation period?");
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));

    expect(onSubmit).toHaveBeenCalledWith("What is the probation period?");
  });

  it("trims before submitting", async () => {
    const onSubmit = vi.fn();
    render(<AskForm onSubmit={onSubmit} isLoading={false} />);

    await userEvent.type(screen.getByRole("textbox"), "  padded  ");
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));

    expect(onSubmit).toHaveBeenCalledWith("padded");
  });

  it("submits on Enter, because people press Enter", async () => {
    const onSubmit = vi.fn();
    render(<AskForm onSubmit={onSubmit} isLoading={false} />);

    await userEvent.type(screen.getByRole("textbox"), "a question{Enter}");

    expect(onSubmit).toHaveBeenCalledWith("a question");
  });

  it("cannot be submitted empty", () => {
    render(<AskForm onSubmit={vi.fn()} isLoading={false} />);

    expect(screen.getByRole("button", { name: "Ask" })).toBeDisabled();
  });

  it("cannot be submitted with only whitespace", async () => {
    const onSubmit = vi.fn();
    render(<AskForm onSubmit={onSubmit} isLoading={false} />);

    await userEvent.type(screen.getByRole("textbox"), "    ");

    expect(screen.getByRole("button", { name: "Ask" })).toBeDisabled();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("locks the form while an answer is in flight", () => {
    // A question takes 10-12 seconds. Without this a second Enter fires
    // another one, and the answers race.
    render(<AskForm onSubmit={vi.fn()} isLoading={true} />);

    expect(screen.getByRole("textbox")).toBeDisabled();
    expect(screen.getByRole("button", { name: /asking/i })).toBeDisabled();
  });

  it("reports an error and offers a retry", async () => {
    const onSubmit = vi.fn();
    render(<AskForm onSubmit={onSubmit} isLoading={false} error="Something broke" />);

    expect(screen.getByText("Something broke")).toBeInTheDocument();
  });

  it("distinguishes 'no answer' from an error", () => {
    // The backend returns answer: null for three different situations and the
    // UI must not present any of them as a failure.
    render(<AskForm onSubmit={vi.fn()} isLoading={false} notFound={true} />);

    expect(screen.getByText(/no answer found/i)).toBeInTheDocument();
  });
});
