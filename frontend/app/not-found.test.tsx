import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import NotFound from "./not-found";

describe("not-found screen", () => {
  it("says in Polish that the page does not exist", () => {
    render(<NotFound />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Nie ma takiej strony");
  });

  // Acceptance criterion 4: its own look and a way back, not a dead end.
  it("offers a way back to the landing page", () => {
    render(<NotFound />);

    expect(screen.getByRole("link", { name: "Wróć na stronę główną" })).toHaveAttribute(
      "href",
      "/",
    );
  });

  it("shows no status code", () => {
    render(<NotFound />);

    expect(document.body.textContent).not.toContain("404");
  });
});
