import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ErrorScreen from "./error";

function thrown(message: string): Error & { digest?: string } {
  return Object.assign(new Error(message), { digest: "d1g3st" });
}

describe("error screen", () => {
  it("says in Polish that something went wrong", () => {
    render(<ErrorScreen error={thrown("boom")} reset={vi.fn()} />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Coś poszło nie tak");
  });

  it("retries the route when asked to", () => {
    const reset = vi.fn();
    render(<ErrorScreen error={thrown("boom")} reset={reset} />);

    fireEvent.click(screen.getByRole("button", { name: "Wyświetl ponownie" }));

    expect(reset).toHaveBeenCalledOnce();
  });

  // Acceptance criterion 4: a way back, so a route that keeps throwing is
  // not a trap.
  it("offers a way back to the landing page", () => {
    render(<ErrorScreen error={thrown("boom")} reset={vi.fn()} />);

    expect(screen.getByRole("link", { name: "Wróć na stronę główną" })).toHaveAttribute(
      "href",
      "/",
    );
  });

  // Acceptance criterion 5, and the reason `error` is never destructured in
  // the component: the thrown message is the likeliest carrier of a provider
  // name, a prompt fragment or a stack trace anywhere in the frontend.
  it("renders nothing from the thrown error, neither message nor digest", () => {
    render(
      <ErrorScreen
        error={thrown("provider Foo refused: system prompt token sk-secret")}
        reset={vi.fn()}
      />,
    );

    expect(document.body.textContent).not.toContain("Foo");
    expect(document.body.textContent).not.toContain("sk-secret");
    expect(document.body.textContent).not.toContain("system prompt");
    expect(document.body.textContent).not.toContain("d1g3st");
    expect(document.body.textContent).not.toContain("500");
  });
});
