import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import AccountPage from "./page";

describe("account route", () => {
  it("renders the Polish heading and placeholder copy", () => {
    render(<AccountPage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Konto");
    expect(screen.getByText(/pojawi się tutaj wkrótce/)).toBeInTheDocument();
  });
});
