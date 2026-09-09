import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { clearPanelToken, panelLogout, readPanelToken, storePanelToken } from "@/lib/panel-client";

import PanelNav from "./PanelNav";

const replace = vi.fn();
const router = { replace, push: vi.fn(), refresh: vi.fn() };
let pathname = "/panel/documents";

vi.mock("next/navigation", () => ({
  useRouter: () => router,
  usePathname: () => pathname,
}));

vi.mock("@/lib/panel-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/panel-client")>();
  return { ...actual, panelLogout: vi.fn(async () => actual.clearPanelToken()) };
});

const logoutMock = vi.mocked(panelLogout);

beforeEach(() => {
  clearPanelToken();
  replace.mockReset();
  logoutMock.mockClear();
  pathname = "/panel/documents";
});

describe("PanelNav", () => {
  it("offers a way to every panel screen an editor may use", () => {
    window.sessionStorage.setItem("bilingers.panel.role", "editor");
    render(<PanelNav />);

    expect(screen.getByRole("link", { name: "Dokumenty" })).toHaveAttribute(
      "href",
      "/panel/documents",
    );
    expect(screen.getByRole("link", { name: "Bezpieczeństwo" })).toHaveAttribute(
      "href",
      "/panel/security",
    );
  });

  it("does not offer the journal to somebody the backend would refuse", () => {
    // Administrators only. Offering it to an editor is offering a 403.
    window.sessionStorage.setItem("bilingers.panel.role", "editor");
    render(<PanelNav />);

    expect(screen.queryByRole("link", { name: "Dziennik zmian" })).not.toBeInTheDocument();
  });

  it("offers the journal to an administrator", () => {
    window.sessionStorage.setItem("bilingers.panel.role", "admin");
    render(<PanelNav />);

    expect(screen.getByRole("link", { name: "Dziennik zmian" })).toHaveAttribute(
      "href",
      "/panel/audit",
    );
  });

  it("ends the session on the server and locally, then leaves", async () => {
    // Before this existed the only way out was closing the tab, which left the
    // token live on the server for the rest of its twelve hours.
    storePanelToken("session-token");
    render(<PanelNav />);

    fireEvent.click(screen.getByRole("button", { name: "Wyloguj się" }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/panel/login"));
    expect(logoutMock).toHaveBeenCalled();
    expect(readPanelToken()).toBeNull();
  });

  it("leaves even when the backend does not answer the logout", async () => {
    storePanelToken("session-token");
    logoutMock.mockRejectedValueOnce(new Error("network"));
    render(<PanelNav />);

    fireEvent.click(screen.getByRole("button", { name: "Wyloguj się" }));

    await waitFor(() => expect(readPanelToken()).toBeNull());
  });

  it("draws nothing on the login screen", () => {
    pathname = "/panel/login";
    render(<PanelNav />);

    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Wyloguj się" })).not.toBeInTheDocument();
  });
});
