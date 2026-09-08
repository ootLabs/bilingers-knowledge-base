import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { clearPanelToken, storePanelToken } from "@/lib/panel-client";

import PanelGuard from "./PanelGuard";

const replace = vi.fn();
// A stable object, like the real Next router. The panel screens put
// `useSessionRecovery` in a dependency list, so a router whose identity changed
// on every render would make their load effect refire forever.
const router = { replace, push: vi.fn(), refresh: vi.fn() };
let pathname = "/panel/documents";

vi.mock("next/navigation", () => ({
  useRouter: () => router,
  usePathname: () => pathname,
}));

beforeEach(() => {
  replace.mockReset();
  clearPanelToken();
  pathname = "/panel/documents";
});

describe("PanelGuard", () => {
  it("sends someone with no token to the login screen", async () => {
    render(
      <PanelGuard>
        <p>Lista dokumentow</p>
      </PanelGuard>,
    );

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/panel/login"));
  });

  it("never renders the panel while it is deciding", () => {
    // One frame of the real screen is one frame of requests with no token and
    // a screenful of failures on the way to the login form.
    render(
      <PanelGuard>
        <p>Lista dokumentow</p>
      </PanelGuard>,
    );

    expect(screen.queryByText("Lista dokumentow")).not.toBeInTheDocument();
    expect(screen.getByText("Sprawdzamy dostęp")).toBeInTheDocument();
  });

  it("lets a session through", async () => {
    storePanelToken("panel-token");

    render(
      <PanelGuard>
        <p>Lista dokumentow</p>
      </PanelGuard>,
    );

    expect(await screen.findByText("Lista dokumentow")).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });

  it("does not redirect the login screen to itself", async () => {
    pathname = "/panel/login";

    render(
      <PanelGuard>
        <p>Formularz logowania</p>
      </PanelGuard>,
    );

    expect(await screen.findByText("Formularz logowania")).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });
});
