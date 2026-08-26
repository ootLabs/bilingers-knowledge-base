import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import ChatPage from "./page";

// Rendering itself is covered by PlaceholderRoute.test.tsx, this only
// checks that this route wires up the chat translation keys, not someone
// else's.
describe("chat route", () => {
  it("renders the chat heading", () => {
    render(<ChatPage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Czat");
  });
});
