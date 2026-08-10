import type { ReactNode } from "react";

/**
 * The heading that names a block of a page.
 *
 * Exported separately because forms cannot use `Section` - they own their own
 * `<form>` element and the elevated card style that goes with it - but they
 * still need to label themselves the same way. Without this the label styling
 * gets retyped per page and drifts, which is how `admin/users` ended up with
 * title-case headings while the case pages used uppercase ones.
 */
export function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <h2 className="text-xs font-medium text-subtle uppercase tracking-wide">
      {children}
    </h2>
  );
}

/**
 * A titled block on a detail page.
 *
 * The case detail page had grown four different treatments for the same idea:
 * some sections were cards with an uppercase micro-label, one was a bare
 * heading with no card, one was an icon empty-state floating on the page
 * background. Reading down the page, nothing looked related to anything else.
 * One component means a section cannot invent its own look.
 *
 * `action` is for the control that belongs to the section rather than to the
 * page - the Documents upload button, for instance - so it sits on the title
 * row instead of being wedged into the body.
 */
export function Section({
  title,
  action,
  variant = "card",
  children,
}: {
  title: string;
  action?: ReactNode;
  /**
   * `card` for a discrete object you could lift off the page - a document
   * collection, one round of review, the ask tool. `plain` for content that
   * belongs to the page itself, where a card adds a border and no meaning.
   * Boxing everything equally is its own failure: six identical cards give the
   * case summary the same weight as a single Edit link.
   */
  variant?: "card" | "plain";
  children: ReactNode;
}) {
  return (
    <section
      className={
        variant === "card"
          ? "bg-surface border border-border rounded-lg px-5 py-4"
          : ""
      }
    >
      <div className="flex items-center justify-between gap-4 mb-3">
        <SectionLabel>{title}</SectionLabel>
        {action}
      </div>
      {children}
    </section>
  );
}
