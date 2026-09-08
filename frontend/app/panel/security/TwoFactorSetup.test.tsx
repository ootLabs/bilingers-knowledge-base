import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PanelRequestError } from "@/lib/panel-client";
import {
  confirmTwoFactor,
  disableTwoFactor,
  getTwoFactorStatus,
  startTwoFactorEnrolment,
} from "@/lib/panel-two-factor";

import TwoFactorSetup from "./TwoFactorSetup";

// A stable object, like the real Next router: a router whose identity changed
// on every render would make the screens' load effect refire forever.
const router = { replace: vi.fn(), push: vi.fn(), refresh: vi.fn() };

vi.mock("next/navigation", () => ({
  useRouter: () => router,
  usePathname: () => "/panel/security",
}));

vi.mock("@/lib/panel-two-factor", () => ({
  getTwoFactorStatus: vi.fn(),
  startTwoFactorEnrolment: vi.fn(),
  confirmTwoFactor: vi.fn(),
  disableTwoFactor: vi.fn(),
}));

const getStatus = vi.mocked(getTwoFactorStatus);
const startEnrolment = vi.mocked(startTwoFactorEnrolment);
const confirm = vi.mocked(confirmTwoFactor);
const disable = vi.mocked(disableTwoFactor);

beforeEach(() => {
  getStatus.mockReset();
  startEnrolment.mockReset();
  confirm.mockReset();
  disable.mockReset();
});

describe("TwoFactorSetup", () => {
  it("explains what to do without using the word TOTP", async () => {
    // The reader is an editor, not an engineer. If the instructions need a
    // glossary, nobody switches this on.
    getStatus.mockResolvedValue({ enabled: false, unusedBackupCodes: 0 });
    render(<TwoFactorSetup />);

    expect(
      await screen.findByText(/Dodatkowe zabezpieczenie jest wyłączone/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Google Authenticator/)).toBeInTheDocument();
    expect(screen.queryByText(/TOTP/i)).not.toBeInTheDocument();
  });

  it("shows the key to type in, then the printed codes once it is confirmed", async () => {
    getStatus.mockResolvedValue({ enabled: false, unusedBackupCodes: 0 });
    startEnrolment.mockResolvedValue({
      secret: "JBSWY3DPEHPK3PXP",
      otpauthUri: "otpauth://totp/x",
    });
    confirm.mockResolvedValue(["ABCD-EFGH-JKLM", "NPQR-STUV-WXYZ"]);
    render(<TwoFactorSetup />);
    await screen.findByText(/Dodatkowe zabezpieczenie jest wyłączone/);

    fireEvent.click(screen.getByRole("button", { name: "Włącz dodatkowe zabezpieczenie" }));
    expect(await screen.findByText("JBSWY3DPEHPK3PXP")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Kod z aplikacji"), {
      target: { value: "123456" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Potwierdź i włącz" }));

    expect(await screen.findByText("ABCD-EFGH-JKLM")).toBeInTheDocument();
    expect(screen.getByText("NPQR-STUV-WXYZ")).toBeInTheDocument();
    expect(confirm).toHaveBeenCalledWith("123456");
  });

  it("says a wrong confirmation code was wrong, and keeps the key on screen", async () => {
    getStatus.mockResolvedValue({ enabled: false, unusedBackupCodes: 0 });
    startEnrolment.mockResolvedValue({
      secret: "JBSWY3DPEHPK3PXP",
      otpauthUri: "otpauth://totp/x",
    });
    // A wrong code is its own answer, not "you are signed out": the backend
    // returns 422 rather than 401 precisely so a typo does not end the session.
    confirm.mockRejectedValue(new PanelRequestError("invalid_code"));
    render(<TwoFactorSetup />);
    await screen.findByText(/Dodatkowe zabezpieczenie jest wyłączone/);
    fireEvent.click(screen.getByRole("button", { name: "Włącz dodatkowe zabezpieczenie" }));
    await screen.findByText("JBSWY3DPEHPK3PXP");

    fireEvent.change(screen.getByLabelText("Kod z aplikacji"), {
      target: { value: "000000" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Potwierdź i włącz" }));

    expect(await screen.findByText("Ten kod się nie zgadza")).toBeInTheDocument();
    expect(screen.getByText("JBSWY3DPEHPK3PXP")).toBeInTheDocument();
  });

  it("will not switch it off without a code", async () => {
    // A stolen session must not be able to remove the thing that makes it
    // useless.
    getStatus.mockResolvedValue({ enabled: true, unusedBackupCodes: 7 });
    render(<TwoFactorSetup />);
    await screen.findByText(/Dodatkowe zabezpieczenie jest włączone/);

    expect(
      screen.getByRole("button", { name: "Wyłącz dodatkowe zabezpieczenie" }),
    ).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Kod z aplikacji lub kod zapasowy"), {
      target: { value: "123456" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Wyłącz dodatkowe zabezpieczenie" }));

    await waitFor(() => expect(disable).toHaveBeenCalledWith("123456"));
  });

  it("says how much paper is left before the phone goes missing", async () => {
    getStatus.mockResolvedValue({ enabled: true, unusedBackupCodes: 7 });
    render(<TwoFactorSetup />);

    expect(
      await screen.findByText("Pozostało niewykorzystanych kodów zapasowych: 7."),
    ).toBeInTheDocument();
  });

  it("reports a missing encryption key as our fault, not the editor's", async () => {
    getStatus.mockResolvedValue({ enabled: false, unusedBackupCodes: 0 });
    startEnrolment.mockRejectedValue(new PanelRequestError("two_factor_not_configured"));
    render(<TwoFactorSetup />);
    await screen.findByText(/Dodatkowe zabezpieczenie jest wyłączone/);

    fireEvent.click(screen.getByRole("button", { name: "Włącz dodatkowe zabezpieczenie" }));

    expect(await screen.findByText("Nie możemy teraz sprawdzić kodu")).toBeInTheDocument();
  });
});
