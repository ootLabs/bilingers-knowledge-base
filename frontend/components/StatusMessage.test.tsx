import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import StatusMessage from "./StatusMessage";

describe("StatusMessage", () => {
  it("renders the translated title and description for the given keys", () => {
    render(
      <StatusMessage
        tone="info"
        titleKey="chat.empty.title"
        descriptionKey="chat.empty.description"
      />,
    );

    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent(
      "Nie zadano jeszcze pytania",
    );
    expect(screen.getByText(/Odpowiedź pojawi się tutaj/)).toBeInTheDocument();
  });

  // The tone class is what carries the visual distinction between a fault
  // and a conversion point, so it is worth pinning.
  it.each([
    ["info", "status-message--info"],
    ["error", "status-message--error"],
    ["limit", "status-message--limit"],
  ] as const)("marks the %s tone on the container", (tone, className) => {
    const { container } = render(
      <StatusMessage tone={tone} titleKey="notFound.title" descriptionKey="notFound.description" />,
    );

    expect(container.querySelector(`.${className}`)).toBeInTheDocument();
  });

  it("calls the retry handler when the retry action is used", () => {
    const onRetry = vi.fn();
    render(
      <StatusMessage
        tone="error"
        titleKey="errors.unreachable.title"
        descriptionKey="errors.unreachable.description"
        action={{ kind: "retry", labelKey: "errors.retry", onRetry }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Spróbuj ponownie" }));

    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("renders a link action pointing where it was told", () => {
    render(
      <StatusMessage
        tone="limit"
        titleKey="errors.limit_reached.title"
        descriptionKey="errors.limit_reached.description"
        action={{ kind: "link", labelKey: "errors.limit_reached.action", href: "/account" }}
      />,
    );

    expect(screen.getByRole("link", { name: "Załóż darmowe konto" })).toHaveAttribute(
      "href",
      "/account",
    );
  });

  it("renders no action when none is given", () => {
    render(
      <StatusMessage tone="info" titleKey="notFound.title" descriptionKey="notFound.description" />,
    );

    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});
