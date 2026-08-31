import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import Home from "./page";

describe("landing page", () => {
  it("renders the product name as the top heading", () => {
    render(<Home />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Bilingers");
  });

  it("describes the product in Polish", () => {
    render(<Home />);
    expect(screen.getByText(/Inteligentna baza wiedzy o dwuj/i)).toBeInTheDocument();
  });

  it("shows the API URL it will talk to", () => {
    // A blank or wrong value here is the usual cause of "the app loads but
    // nothing works", so it is surfaced on the page and asserted on.
    render(<Home />);
    expect(document.querySelector("code")?.textContent).toMatch(/^https?:\/\//);
  });

  it("links to the chat route as the primary call to action", () => {
    render(<Home />);
    expect(screen.getByRole("link", { name: /czatu/i })).toHaveAttribute("href", "/chat");
  });
});

describe("API URL configuration", () => {
  const original = process.env.NEXT_PUBLIC_API_URL;

  afterEach(() => {
    process.env.NEXT_PUBLIC_API_URL = original;
    vi.resetModules();
  });

  it("uses the configured value when one is present", async () => {
    process.env.NEXT_PUBLIC_API_URL = "https://api.bilingers.test";
    vi.resetModules();
    const { default: FreshHome } = await import("./page");

    render(<FreshHome />);
    expect(document.querySelector("code")?.textContent).toBe(
      "https://api.bilingers.test",
    );
  });

  it("falls back to the local backend when nothing is configured", async () => {
    delete process.env.NEXT_PUBLIC_API_URL;
    vi.resetModules();
    const { default: FreshHome } = await import("./page");

    render(<FreshHome />);
    expect(document.querySelector("code")?.textContent).toBe("http://localhost:8000");
  });
});
