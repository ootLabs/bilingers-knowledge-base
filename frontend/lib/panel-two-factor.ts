// The panel's second factor (T-83), on top of panel-client.ts.
import { PanelRequestError, panelRequest, toPanelFailure } from "./panel-client";

/**
 * Turn "this request was unacceptable" into "that code was wrong".
 *
 * The two calls below send exactly one field, so there is nothing else a 422
 * could be about, and the knowledge lives here rather than in the client, which
 * has no way to tell one 422 from another without reading a body it never
 * reads. The backend answers 422 rather than 401 for the same reason from its
 * side: a mistyped code must not look like a session that stopped working, or
 * the editor gets signed out for a typo.
 */
function asCodeFailure(error: unknown): never {
  throw toPanelFailure(error) === "invalid_input"
    ? new PanelRequestError("invalid_code")
    : error;
}

export type TwoFactorStatus = {
  enabled: boolean;
  /** Zero means the printed sheet is spent, which is worth knowing early. */
  unusedBackupCodes: number;
};

export type TwoFactorEnrolment = {
  /** The key as a person types it. Readable exactly once, here. */
  secret: string;
  /** The same key as an authenticator app expects it. */
  otpauthUri: string;
};

export async function getTwoFactorStatus(): Promise<TwoFactorStatus> {
  const raw = await panelRequest<{ enabled: boolean; unused_backup_codes: number }>(
    "/api/panel/users/me/two-factor",
  );
  return { enabled: raw.enabled, unusedBackupCodes: raw.unused_backup_codes };
}

/** Mint a secret. Nothing is switched on until a live code confirms it. */
export async function startTwoFactorEnrolment(): Promise<TwoFactorEnrolment> {
  const raw = await panelRequest<{ secret: string; otpauth_uri: string }>(
    "/api/panel/users/me/two-factor",
    { method: "POST" },
  );
  return { secret: raw.secret, otpauthUri: raw.otpauth_uri };
}

/** Confirm and receive the printable codes. They are never readable again. */
export async function confirmTwoFactor(code: string): Promise<string[]> {
  try {
    const raw = await panelRequest<{ codes: string[] }>(
      "/api/panel/users/me/two-factor/confirm",
      { method: "POST", body: { code } },
    );
    return raw.codes;
  } catch (error) {
    asCodeFailure(error);
  }
}

/** Switch it off, proving you can still pass it. */
export async function disableTwoFactor(code: string): Promise<void> {
  try {
    await panelRequest<void>("/api/panel/users/me/two-factor/disable", {
      method: "POST",
      body: { code },
    });
  } catch (error) {
    asCodeFailure(error);
  }
}
