import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  clearPanelToken,
  panelLogin,
  panelLogout,
  panelRequest,
  PanelRequestError,
  readPanelToken,
  storePanelToken,
  toPanelFailure,
} from "./panel-client";

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status < 400,
    status,
    json: async () => body,
    // Reading this would fail the test that says a failed body is never read.
    text: async () => {
      throw new Error("the body of a failed response must never be read");
    },
  } as unknown as Response;
}

function failing(status: number, headers: Record<string, string> = {}): Response {
  return {
    ok: false,
    status,
    headers: { get: (name: string) => headers[name] ?? null },
    json: async () => {
      throw new Error("the body of a failed response must never be read");
    },
  } as unknown as Response;
}

const SESSION_BODY = {
  token: "session-token",
  expires_at: "2026-09-09T08:00:00Z",
  user: { email: "redaktorka@fundacja.test", role: "editor" },
};

beforeEach(() => {
  clearPanelToken();
});

afterEach(() => {
  vi.unstubAllGlobals();
  clearPanelToken();
});

describe("panelLogin", () => {
  it("remembers the token for the rest of the tab", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(201, SESSION_BODY)));

    const session = await panelLogin({ email: "a@b.test", password: "haslo" });

    expect(session.email).toBe("redaktorka@fundacja.test");
    expect(readPanelToken()).toBe("session-token");
  });

  it("calls a refused login invalid_credentials, not an expired session", async () => {
    // There is no session yet, so treating a 401 as an expiry would bounce the
    // editor to the screen she is already standing on.
    vi.stubGlobal("fetch", vi.fn(async () => failing(401)));

    await expect(panelLogin({ email: "a@b.test", password: "x" })).rejects.toMatchObject({
      failure: "invalid_credentials",
    });
    expect(readPanelToken()).toBeNull();
  });

  it("reads the second factor signal from a header, not from the body", async () => {
    // The rule that a failed response's body is never read is worth more than
    // the convenience of putting this in `detail`, so the backend sends it as a
    // header and this is where it is picked up.
    vi.stubGlobal("fetch", vi.fn(async () => failing(401, { "X-Second-Factor": "required" })));

    await expect(panelLogin({ email: "a@b.test", password: "haslo" })).rejects.toMatchObject({
      failure: "second_factor_required",
    });
    expect(readPanelToken()).toBeNull();
  });

  it.each([
    [403, "forbidden"],
    [409, "conflict"],
    [422, "invalid_input"],
    [429, "too_many_attempts"],
    [503, "database_unavailable"],
    [418, "unreachable"],
  ])("maps %i to %s", async (status, failure) => {
    vi.stubGlobal("fetch", vi.fn(async () => failing(status)));

    await expect(panelLogin({ email: "a@b.test", password: "x" })).rejects.toMatchObject({
      failure,
    });
  });

  it("reports an unreachable backend rather than throwing the network error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch: db-prod-01");
      }),
    );

    await expect(panelLogin({ email: "a@b.test", password: "x" })).rejects.toMatchObject({
      failure: "unreachable",
    });
  });
});

describe("panelRequest", () => {
  it("refuses to call anything without a token", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await expect(panelRequest("/api/panel/documents")).rejects.toMatchObject({
      failure: "not_authenticated",
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("sends the token as a bearer credential", async () => {
    storePanelToken("session-token");
    // The parameters are declared, unused, so `mock.calls` is typed as the pair
    // this test reads back. Without them it is an empty tuple and the cast
    // below is the error `npm run typecheck` reports.
    const fetchMock = vi.fn(async (_path: string, _init: RequestInit) =>
      jsonResponse(200, []),
    );
    vi.stubGlobal("fetch", fetchMock);

    await panelRequest("/api/panel/documents");

    const [, init] = fetchMock.mock.calls[0];
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer session-token");
  });

  it("tells a missing encryption key apart from a database outage", async () => {
    // Both are 503 on the same endpoint, and the copy differs in what it asks
    // the editor to do: wait, or write to whoever runs the system. The header
    // is what separates them without reading the body.
    storePanelToken("session-token");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => failing(503, { "X-Second-Factor": "not-configured" })),
    );

    await expect(panelRequest("/api/panel/users/me/two-factor")).rejects.toMatchObject({
      failure: "two_factor_not_configured",
    });
  });

  it("still reads a plain 503 as the database being away", async () => {
    storePanelToken("session-token");
    vi.stubGlobal("fetch", vi.fn(async () => failing(503)));

    await expect(panelRequest("/api/panel/documents")).rejects.toMatchObject({
      failure: "database_unavailable",
    });
  });

  it("drops a token the backend has stopped accepting", async () => {
    // Expired, revoked, or the account switched off: which of them it was is
    // not the client's business, and keeping the token would leave every later
    // screen failing on it.
    storePanelToken("stale-token");
    vi.stubGlobal("fetch", vi.fn(async () => failing(401)));

    await expect(panelRequest("/api/panel/documents")).rejects.toMatchObject({
      failure: "not_authenticated",
    });
    expect(readPanelToken()).toBeNull();
  });

  it("returns nothing for a 204 instead of parsing an empty body", async () => {
    storePanelToken("session-token");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: true, status: 204 }) as unknown as Response),
    );

    await expect(panelRequest("/api/panel/sessions/current", { method: "DELETE" })).resolves.toBe(
      undefined,
    );
  });
});

describe("panelLogout", () => {
  it("forgets the token even when the backend does not answer", async () => {
    storePanelToken("session-token");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );

    await panelLogout();

    expect(readPanelToken()).toBeNull();
  });
});

describe("toPanelFailure", () => {
  it("degrades anything it does not recognise", () => {
    expect(toPanelFailure(new Error("boom"))).toBe("unreachable");
    expect(toPanelFailure(new PanelRequestError("conflict"))).toBe("conflict");
  });
});
