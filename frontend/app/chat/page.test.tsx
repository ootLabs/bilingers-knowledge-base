import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import ChatPage from "./page";

describe("chat route", () => {
  it("renders the Polish heading and placeholder copy", () => {
    render(<ChatPage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Czat");
    expect(screen.getByText(/pojawi się tutaj wkrótce/)).toBeInTheDocument();
  });
});
