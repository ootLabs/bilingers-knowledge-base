import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PanelRequestError, panelLogin } from "@/lib/panel-client";

import LoginForm from "./LoginForm";

const replace = vi.fn();
// A stable object, like the real Next router. The panel screens put
// `useSessionRecovery` in a dependency list, so a router whose identity changed
// on every render would make their load effect refire forever.
const router = { replace, push: vi.fn(), refresh: vi.fn() };

vi.mock("next/navigation", () => ({
  useRouter: () => router,
  usePathname: () => "/panel/login",
}));

vi.mock("@/lib/panel-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/panel-client")>();
  return { ...actual, panelLogin: vi.fn() };
});

const panelLoginMock = vi.mocked(panelLogin);

function fillIn(email = "redaktorka@fundacja.test", password = "haslo-do-panelu") {
  fireEvent.change(screen.getByLabelText("Adres e-mail"), { target: { value: email } });
  fireEvent.change(screen.getByLabelText("Hasło"), { target: { value: password } });
  fireEvent.click(screen.getByRole("button", { name: "Zaloguj się" }));
}

beforeEach(() => {
  panelLoginMock.mockReset();
  replace.mockReset();
});

describe("LoginForm", () => {
  it("will not submit until both fields are filled in", () => {
    render(<LoginForm />);

    expect(screen.getByRole("button", { name: "Zaloguj się" })).toBeDisabled();
  });

  it("sends the editor to the documents screen after a successful login", async () => {
    panelLoginMock.mockResolvedValue({
      token: "t",
      expiresAt: "2026-09-09T00:00:00Z",
      email: "redaktorka@fundacja.test",
      role: "editor",
    });
    render(<LoginForm />);

    fillIn();

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/panel/documents"));
  });

  it("answers a wrong password exactly as it answers an unknown account", async () => {
    // The backend gives both the same 401 with the same timing so that nobody
    // can find out which addresses have an account. A screen that told them
    // apart would hand that back.
    panelLoginMock.mockRejectedValue(new PanelRequestError("invalid_credentials"));
    render(<LoginForm />);

    fillIn("nieznany@fundacja.test");
    const unknownAccount = await screen.findByText("Nie udało się zalogować");
    expect(unknownAccount).toBeInTheDocument();

    panelLoginMock.mockRejectedValue(new PanelRequestError("invalid_credentials"));
    fillIn("redaktorka@fundacja.test", "zle-haslo");

    expect(await screen.findByText("Nie udało się zalogować")).toBeInTheDocument();
  });

  it("shows an outage as an outage, not as wrong credentials", async () => {
    // Otherwise the editor spends the whole outage retyping a password that
    // was right the first time.
    panelLoginMock.mockRejectedValue(new PanelRequestError("database_unavailable"));
    render(<LoginForm />);

    fillIn();

    expect(await screen.findByText("Panel jest chwilowo niedostępny")).toBeInTheDocument();
    expect(screen.queryByText("Nie udało się zalogować")).not.toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });

  it("shows the throttle as its own answer", async () => {
    panelLoginMock.mockRejectedValue(new PanelRequestError("too_many_attempts"));
    render(<LoginForm />);

    fillIn();

    expect(await screen.findByText("Za dużo prób z tego miejsca")).toBeInTheDocument();
  });

  it("asks for a code once the backend says the account needs one", async () => {
    panelLoginMock.mockRejectedValueOnce(new PanelRequestError("second_factor_required"));
    render(<LoginForm />);

    expect(screen.queryByLabelText("Kod z aplikacji")).not.toBeInTheDocument();

    fillIn();

    expect(await screen.findByText("Potrzebujemy jeszcze kodu")).toBeInTheDocument();
    const codeField = screen.getByLabelText("Kod z aplikacji");

    panelLoginMock.mockResolvedValueOnce({
      token: "t",
      expiresAt: "2026-09-09T00:00:00Z",
      email: "redaktorka@fundacja.test",
      role: "editor",
    });
    fireEvent.change(codeField, { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "Zaloguj się" }));

    await waitFor(() =>
      expect(panelLoginMock).toHaveBeenLastCalledWith({
        email: "redaktorka@fundacja.test",
        password: "haslo-do-panelu",
        code: "123456",
      }),
    );
  });

  it("says the code was wrong rather than blaming the password", async () => {
    // A mistyped code used to read "Adres e-mail lub hasło się nie zgadzają",
    // which sends somebody whose password was right to an administrator.
    panelLoginMock.mockRejectedValueOnce(new PanelRequestError("invalid_code"));
    render(<LoginForm />);
    fillIn();

    expect(await screen.findByText("Ten kod się nie zgadza")).toBeInTheDocument();
    // And the field is on screen even though this was the first attempt, so
    // there is somewhere to correct it.
    expect(screen.getByLabelText("Kod z aplikacji")).toBeInTheDocument();
  });

  it("keeps the code field on screen after a mistyped code", async () => {
    // Hiding it again would make the person start the whole login over.
    panelLoginMock.mockRejectedValueOnce(new PanelRequestError("second_factor_required"));
    render(<LoginForm />);
    fillIn();
    await screen.findByLabelText("Kod z aplikacji");

    panelLoginMock.mockRejectedValueOnce(new PanelRequestError("invalid_credentials"));
    fireEvent.change(screen.getByLabelText("Kod z aplikacji"), {
      target: { value: "000000" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Zaloguj się" }));

    expect(await screen.findByText("Nie udało się zalogować")).toBeInTheDocument();
    expect(screen.getByLabelText("Kod z aplikacji")).toBeInTheDocument();
  });

  it("degrades an unrecognised failure instead of rendering it", async () => {
    panelLoginMock.mockRejectedValue(new Error("Connection refused to db-prod-01"));
    render(<LoginForm />);

    fillIn();

    expect(await screen.findByText("Nie udało się połączyć")).toBeInTheDocument();
    expect(screen.queryByText(/db-prod-01/)).not.toBeInTheDocument();
  });
});
