import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import QuizPage from "./page";

describe("quiz route", () => {
  it("renders the Polish heading and placeholder copy", () => {
    render(<QuizPage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Quiz");
    expect(screen.getByText(/pojawi się tutaj wkrótce/)).toBeInTheDocument();
  });
});
