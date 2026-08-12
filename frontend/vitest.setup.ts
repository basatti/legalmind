import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// React Testing Library does not unmount between tests on its own outside of
// its own globals setup. Without this, a component from one test is still in
// the document during the next, and queries like getByText start matching the
// previous test's render — which fails in a way that points at the wrong test.
afterEach(() => {
  cleanup();
});
