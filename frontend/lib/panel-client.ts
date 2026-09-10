// The panel's own HTTP client. A separate file from api-client.ts, not an
// extension of it: `ChatFailure` is a closed union for the parent-facing path,
// and the panel speaks a different one. 401, 403 and 409 are real answers here
// and meaningless there; the parent's quota (429 as "limit_reached") does not
// exist in the panel at all.
//
// What the two share is exactly one thing, and it is imported rather than
// copied: two definitions of API_URL would let the panel talk to one backend
// while the landing page advertises another.
import { API_URL } from "./api-client";

export type PanelFailure =
  | "invalid_credentials"
  | "second_factor_required"
  | "invalid_code"
  | "two_factor_not_configured"
  | "not_authenticated"
  | "forbidden"
  | "not_found"
  | "conflict"
  | "invalid_input"
  | "file_too_large"
  | "too_many_attempts"
  | "database_unavailable"
  | "unreachable";

// Same closed-union discipline as the chat client: a status the backend starts
// returning that is not listed here degrades to "unreachable" rather than
// reaching a screen as an unhandled shape.
//
// 429 is kept even though the parent's version of it is gone. The backend
// throttles login attempts per IP address (see `app.services.rate_limit`), so
// an editor whose office shares one address can genuinely be turned away, and
// telling her "check your internet connection" would send her looking for a
// fault that is not there.
const FAILURE_BY_STATUS: Record<number, PanelFailure> = {
  400: "invalid_input",
  401: "not_authenticated",
  403: "forbidden",
  404: "not_found",
  409: "conflict",
  // The .docx import is the one endpoint that can answer this (see
  // `app.routers.panel_document_imports`), and it needs its own key rather
  // than `invalid_input`: an oversized file is nothing to do with the title or
  // the body, and without the mapping a 413 degraded to `unreachable`, which
  // told an editor to check her internet connection over a file that arrived
  // perfectly well.
  413: "file_too_large",
  422: "invalid_input",
  429: "too_many_attempts",
  503: "database_unavailable",
};

/** A failed panel call, reduced to a key the copy layer can translate. */
export class PanelRequestError extends Error {
  readonly failure: PanelFailure;

  constructor(failure: PanelFailure) {
    // For a developer reading a stack trace, never for the screen.
    super(`panel request failed: ${failure}`);
    this.name = "PanelRequestError";
    this.failure = failure;
  }
}

/** Anything thrown during a panel call, as a key. Unknown means unreachable. */
export function toPanelFailure(error: unknown): PanelFailure {
  return error instanceof PanelRequestError ? error.failure : "unreachable";
}

// Session storage, not local storage: the token dies with the tab, so a shared
// or public machine does not keep a live session for the next person who opens
// the browser. The decision to hold it in the browser at all (rather than in an
// HttpOnly cookie) is recorded in docs/architecture.md, together with what it
// costs.
const TOKEN_KEY = "bilingers.panel.token";
// Beside the token, and cleared with it. Only the navigation reads it, to
// decide whether to offer the journal, which is administrators only. It is a
// hint for the screen and never a permission: the backend answers 403 to an
// editor whatever this says, the same standing as `PanelGuard`.
const ROLE_KEY = "bilingers.panel.role";

function tokenStore(): Storage | null {
  // Absent during prerender, and it throws outright in a browser configured to
  // block site data. Either way the panel has to render, not crash.
  try {
    return typeof window === "undefined" ? null : window.sessionStorage;
  } catch {
    return null;
  }
}

export function readPanelToken(): string | null {
  const value = tokenStore()?.getItem(TOKEN_KEY) ?? null;
  return value === "" ? null : value;
}

export function storePanelToken(token: string): void {
  try {
    tokenStore()?.setItem(TOKEN_KEY, token);
  } catch {
    // A session that cannot be remembered is still a session that works for
    // this page load; nothing here is worth failing the login over.
  }
}

/** Which role the screen should draw for. Absent means "assume the least". */
export function readPanelRole(): string | null {
  const value = tokenStore()?.getItem(ROLE_KEY) ?? null;
  return value === "" ? null : value;
}

function storePanelRole(role: string): void {
  try {
    tokenStore()?.setItem(ROLE_KEY, role);
  } catch {
    // Same as the token: worth nothing to fail a login over.
  }
}

export function clearPanelToken(): void {
  try {
    const store = tokenStore();
    store?.removeItem(TOKEN_KEY);
    // Together, always. A role left behind after the token is gone would draw
    // an administrator's navigation for whoever logs in next on this tab.
    store?.removeItem(ROLE_KEY);
  } catch {
    // Nothing to do: the token was already unreachable.
  }
}

async function panelFetch(path: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(`${API_URL}${path}`, init);
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") {
      throw error;
    }
    throw new PanelRequestError("unreachable");
  }
}

/**
 * Reduce a failed response to a key.
 *
 * The body is never read, for the same reason `streamAnswer` never reads one:
 * whatever a failing backend puts there can name internals, and the moment it
 * is in hand something eventually renders it. The status is all that is taken.
 */
function failureFor(response: Response): PanelRequestError {
  // The one 503 that is not a database outage: the deployment has no TOTP
  // encryption key, so enrolling and verifying a code cannot work until an
  // operator sets one. Read from the header for the same reason the login form
  // reads the second-factor prompt from one, and it is the same header, so no
  // new CORS entry is needed. Telling these apart matters because the copy
  // differs in what it asks the editor to do: wait, or write to somebody.
  if (
    response.status === 503 &&
    response.headers.get("X-Second-Factor") === "not-configured"
  ) {
    return new PanelRequestError("two_factor_not_configured");
  }
  return new PanelRequestError(FAILURE_BY_STATUS[response.status] ?? "unreachable");
}

export type PanelSession = {
  token: string;
  expiresAt: string;
  email: string;
  role: string;
};

/**
 * Log in and remember the token for the rest of the tab's life.
 *
 * Every refusal the backend can give (unknown address, wrong password, locked
 * account, deactivated account) arrives as one 401 with one timing, and it
 * leaves here as one key. Telling them apart on screen would undo the whole
 * point of the backend answering them identically.
 */
export async function panelLogin({
  email,
  password,
  code,
}: {
  email: string;
  password: string;
  code?: string;
}): Promise<PanelSession> {
  const response = await panelFetch("/api/panel/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(code ? { email, password, code } : { email, password }),
  });

  if (!response.ok) {
    if (response.status === 401) {
      // Read from a header, not from the body: the rule that a failed
      // response's body is never read is worth more than the convenience, and
      // this is the one thing the form genuinely has to know. A 401 that does
      // not carry it is "these credentials do not open a session", not "your
      // session expired" - there is no session yet, and treating it as an
      // expiry would bounce the editor to the screen she is already on.
      // Three answers behind one status, told apart by the header the backend
      // sets (`app.routers.panel_auth`), because a failed response's body is
      // never read. `invalid` is only ever sent after a correct password, to
      // somebody the previous attempt already told that this account has a
      // second factor, so it reveals nothing and it stops the form telling her
      // that a password which was right is wrong.
      const prompt = response.headers.get("X-Second-Factor");
      throw new PanelRequestError(
        prompt === "required"
          ? "second_factor_required"
          : prompt === "invalid"
            ? "invalid_code"
            : "invalid_credentials",
      );
    }
    throw failureFor(response);
  }

  const body = (await response.json()) as {
    token: string;
    expires_at: string;
    user: { email: string; role: string };
  };
  storePanelToken(body.token);
  storePanelRole(body.user.role);
  return {
    token: body.token,
    expiresAt: body.expires_at,
    email: body.user.email,
    role: body.user.role,
  };
}

/**
 * Any other panel call, with the session token attached.
 *
 * A 401 means the token is no longer usable, whatever the reason (expired,
 * revoked, the account switched off). It is dropped here rather than left for
 * each caller to remember, so a stale token cannot survive one screen that
 * forgot to clear it.
 */
export async function panelRequest<T>(
  path: string,
  { method = "GET", body, signal }: { method?: string; body?: unknown; signal?: AbortSignal } = {},
): Promise<T> {
  const token = readPanelToken();
  if (token === null) {
    throw new PanelRequestError("not_authenticated");
  }

  // An upload is sent as it stands. Setting Content-Type by hand on a FormData
  // body drops the multipart boundary the browser generates, and the request
  // arrives at the backend as an empty form with no readable error.
  const isUpload = typeof FormData !== "undefined" && body instanceof FormData;

  const response = await panelFetch(path, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(body === undefined || isUpload ? {} : { "Content-Type": "application/json" }),
    },
    body: body === undefined ? undefined : isUpload ? (body as FormData) : JSON.stringify(body),
    signal,
  });

  if (response.status === 401) {
    clearPanelToken();
    throw new PanelRequestError("not_authenticated");
  }
  if (!response.ok) {
    throw failureFor(response);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

/** End this session on the server as well, then forget the token locally. */
export async function panelLogout(): Promise<void> {
  try {
    await panelRequest<void>("/api/panel/sessions/current", { method: "DELETE" });
  } catch {
    // Logging out has to work even when the backend does not answer: the token
    // is gone from this browser either way, which is what the person asked for.
  } finally {
    clearPanelToken();
  }
}
