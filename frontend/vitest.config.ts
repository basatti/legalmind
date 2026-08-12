import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Vitest rather than Jest, deliberately.
//
// This is Next 16 / React 19 / Turbopack. Jest needs its own transform and ESM
// configuration to sit on top of that, and it is configuration that goes stale
// with every Next upgrade. Vitest reads this project's TypeScript directly, so
// the only thing to keep in step is the path alias below, and its API is
// Jest-compatible — `describe`/`it`/`expect`/`vi.mock` — so nothing new has to
// be learned to read these tests.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    // Only our own tests. Without this, `next build` output and node_modules
    // get walked on every run.
    include: ["{app,components,lib}/**/*.test.{ts,tsx}"],
  },
  resolve: {
    alias: {
      // Mirrors `paths: { "@/*": ["./*"] }` in tsconfig.json. Two places, and
      // they must agree — a test importing "@/lib/permissions" resolves
      // through this one, not through tsconfig.
      "@": fileURLToPath(new URL("./", import.meta.url)),
    },
  },
});
