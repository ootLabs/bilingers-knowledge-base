import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// Without this, one test's DOM leaks into the next and failures get confusing.
afterEach(() => {
  cleanup();
});

// next/font/google relies on a build-time loader that only exists inside
// Next's own webpack/SWC pipeline, not Vite's. Vitest needs a stand-in that
// returns the same shape (className, variable) without doing real font work.
vi.mock("next/font/google", () => ({
  Poppins: () => ({ className: "poppins-mock", variable: "--font-poppins" }),
}));
