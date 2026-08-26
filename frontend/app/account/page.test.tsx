import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import AccountPage from "./page";

// Rendering itself is covered by PlaceholderRoute.test.tsx, this only
// checks that this route wires up the account translation keys, not
// someone else's.
describe("account route", () => {
  it("renders the account heading", () => {
    render(<AccountPage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Konto");
  });
});
