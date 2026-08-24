import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import SiteHeader from "./SiteHeader";

describe("SiteHeader", () => {
  it("links the brand to the landing page", () => {
    render(<SiteHeader />);
    expect(screen.getByRole("link", { name: "Bilingers" })).toHaveAttribute("href", "/");
  });

  it("renders a link to every skeleton route with Polish labels", () => {
    render(<SiteHeader />);

    expect(screen.getByRole("link", { name: "Strona główna" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "Czat" })).toHaveAttribute("href", "/chat");
    expect(screen.getByRole("link", { name: "Quiz" })).toHaveAttribute("href", "/quiz");
    expect(screen.getByRole("link", { name: "Konto" })).toHaveAttribute("href", "/account");
  });

  it("labels the navigation landmark for assistive technology", () => {
    render(<SiteHeader />);
    expect(screen.getByRole("navigation", { name: "Główna nawigacja" })).toBeInTheDocument();
  });
});
