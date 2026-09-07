import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import PlaceholderRoute from "./PlaceholderRoute";

describe("PlaceholderRoute", () => {
  it("renders the translated heading and placeholder copy for the given keys", () => {
    render(
      <PlaceholderRoute headingKey="quiz.heading" placeholderKey="quiz.placeholder" />,
    );
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Quiz");
    expect(screen.getByText(/pojawi się tutaj wkrótce/)).toBeInTheDocument();
  });
});
