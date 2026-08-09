/**
 * Shared display formatting.
 *
 * The locale is deliberately left to the browser — this is an Arabic-first
 * product and pinning en-US would be wrong. What is not left to chance is the
 * *shape*: one call site using the bare `toLocaleDateString()` and another
 * passing options put two different date formats on the same screen.
 */

export function formatDate(isoString: string): string {
  return new Date(isoString).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}
