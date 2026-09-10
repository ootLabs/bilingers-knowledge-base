import { beforeEach, describe, expect, it, vi } from "vitest";

import { PanelRequestError, panelRequest } from "./panel-client";
import {
  confirmTwoFactor,
  disableTwoFactor,
  getTwoFactorStatus,
  startTwoFactorEnrolment,
} from "./panel-two-factor";

vi.mock("./panel-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./panel-client")>();
  return { ...actual, panelRequest: vi.fn() };
});

const request = vi.mocked(panelRequest);

beforeEach(() => {
  request.mockReset();
});

describe("panel-two-factor", () => {
  it("reads the status, including how much paper is left", async () => {
    request.mockResolvedValue({ enabled: true, unused_backup_codes: 7 });

    await expect(getTwoFactorStatus()).resolves.toEqual({
      enabled: true,
      unusedBackupCodes: 7,
    });
  });

  it("returns the key in both forms when enrolment starts", async () => {
    request.mockResolvedValue({ secret: "JBSWY3DPEHPK3PXP", otpauth_uri: "otpauth://totp/x" });

    await expect(startTwoFactorEnrolment()).resolves.toEqual({
      secret: "JBSWY3DPEHPK3PXP",
      otpauthUri: "otpauth://totp/x",
    });
  });

  it("hands back the printed codes on confirmation", async () => {
    request.mockResolvedValue({ codes: ["ABCD-EFGH-JKLM"] });

    await expect(confirmTwoFactor("123456")).resolves.toEqual(["ABCD-EFGH-JKLM"]);
    expect(request).toHaveBeenCalledWith("/api/panel/users/me/two-factor/confirm", {
      method: "POST",
      body: { code: "123456" },
    });
  });

  it("calls a rejected code a rejected code, not unusable input", async () => {
    // These calls send exactly one field, so a 422 can only be about the code.
    // The backend answers 422 rather than 401 for the matching reason: a typo
    // must not look like a session that stopped working.
    request.mockRejectedValue(new PanelRequestError("invalid_input"));

    await expect(confirmTwoFactor("000000")).rejects.toMatchObject({
      failure: "invalid_code",
    });
    await expect(disableTwoFactor("000000")).rejects.toMatchObject({
      failure: "invalid_code",
    });
  });

  it("passes every other failure through untouched", async () => {
    request.mockRejectedValue(new PanelRequestError("not_authenticated"));

    await expect(disableTwoFactor("123456")).rejects.toMatchObject({
      failure: "not_authenticated",
    });
  });
});
