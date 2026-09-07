import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import TypingIndicator from "./TypingIndicator";

describe("TypingIndicator", () => {
  it("says in Polish that the assistant is writing", () => {
    render(<TypingIndicator />);

    expect(screen.getByText("Asystent pisze")).toBeInTheDocument();
  });

  // The label carries the meaning; the dots are decoration. Without this,
  // a screen reader would read three empty spans after the sentence.
  it("hides the animated dots from assistive technology", () => {
    const { container } = render(<TypingIndicator />);

    expect(container.querySelector(".typing-indicator__dots")).toHaveAttribute(
      "aria-hidden",
      "true",
    );
  });
});
