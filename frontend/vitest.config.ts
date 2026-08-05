import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["app/**/*.test.{ts,tsx}", "components/**/*.test.{ts,tsx}", "lib/**/*.test.ts"],
    coverage: {
      provider: "v8",
      include: ["app/**/*.{ts,tsx}", "components/**/*.{ts,tsx}", "lib/**/*.ts"],
      exclude: ["**/*.test.{ts,tsx}"],
      reporter: ["text", "lcov"],
      // Set just below what the suite currently achieves, so a regression
      // trips the build. The branch figure is lower on purpose: v8 counts
      // branches in transpiled JSX that no test can reach, and writing fake
      // tests to satisfy that number would be worse than the gap it hides.
      thresholds: {
        statements: 90,
        branches: 70,
        functions: 90,
        lines: 90,
      },
    },
  },
});
