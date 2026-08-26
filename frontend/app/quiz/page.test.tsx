import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import QuizPage from "./page";

// Rendering itself is covered by PlaceholderRoute.test.tsx, this only
// checks that this route wires up the quiz translation keys, not someone
// else's.
describe("quiz route", () => {
  it("renders the quiz heading", () => {
    render(<QuizPage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Quiz");
  });
});
