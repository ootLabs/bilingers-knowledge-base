import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ChatPage from "./page";

// The panel's own behavior is covered by ChatPanel.test.tsx. This only
// checks the route renders the chat heading and mounts the panel.
vi.mock("./ChatPanel", () => ({
  default: () => <div data-testid="chat-panel" />,
}));

describe("chat route", () => {
  it("renders the chat heading and the panel", () => {
    render(<ChatPage />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Czat");
    expect(screen.getByTestId("chat-panel")).toBeInTheDocument();
  });
});
