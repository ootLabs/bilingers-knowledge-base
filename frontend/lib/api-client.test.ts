import { afterEach, describe, expect, it, vi } from "vitest";

import { ChatRequestError, createSessionToken, streamAnswer } from "./api-client";

/** A 200 whose body hands back `chunks` one read at a time. */
function streamingResponse(chunks: Uint8Array[]): Response {
  let index = 0;
  return {
    ok: true,
    status: 200,
    body: {
      getReader: () => ({
        read: async () =>
          index < chunks.length
            ? { done: false, value: chunks[index++] }
            : { done: true, value: undefined },
        releaseLock: () => {},
      }),
    },
  } as unknown as Response;
}

function failingResponse(status: number, extra: Partial<Response> = {}): Response {
  return { ok: false, status, body: null, ...extra } as unknown as Response;
}

async function collect(stream: AsyncGenerator<string>): Promise<string> {
  let text = "";
  for await (const chunk of stream) {
    text += chunk;
  }
  return text;
}

function ask(question = "pytanie") {
  return streamAnswer({ question, sessionToken: "a".repeat(32) });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("createSessionToken", () => {
  // A token that does not match the backend's pattern comes back as a 422 on
  // every question, which surfaces as "bad question" rather than "bad token".
  it("matches the pattern the backend enforces on session_token", () => {
    expect(createSessionToken()).toMatch(/^[0-9a-f]{32,64}$/);
  });

  it("mints a different token each time", () => {
    expect(createSessionToken()).not.toBe(createSessionToken());
  });

  // `crypto.randomUUID` is secure-context-only, so it is absent when the app
  // is served over plain http from anything but localhost (a LAN address
  // during a demo). Reaching for it there would throw where the caller
  // expects a token, and the click would produce nothing at all.
  it("does not depend on randomUUID, which is absent outside a secure context", () => {
    vi.stubGlobal("crypto", { getRandomValues: crypto.getRandomValues.bind(crypto) });

    expect(createSessionToken()).toMatch(/^[0-9a-f]{32,64}$/);
  });
});

describe("streamAnswer", () => {
  it("posts the question under the field names the backend expects", async () => {
    const fetchMock = vi.fn().mockResolvedValue(streamingResponse([]));
    vi.stubGlobal("fetch", fetchMock);

    await collect(ask("czy warto?"));

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/chat");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({
      question: "czy warto?",
      session_token: "a".repeat(32),
    });
  });

  it("yields the streamed chunks in order", async () => {
    const encoder = new TextEncoder();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        streamingResponse([encoder.encode("pierwszy "), encoder.encode("drugi")]),
      ),
    );

    expect(await collect(ask())).toBe("pierwszy drugi");
  });

  it("decodes a multi-byte character split across two chunks", async () => {
    // Polish copy is full of these, and decoding each chunk in isolation
    // turns a split character into a replacement glyph mid-answer.
    const encoded = new TextEncoder().encode("ą");
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(streamingResponse([encoded.slice(0, 1), encoded.slice(1)])),
    );

    expect(await collect(ask())).toBe("ą");
  });

  it.each([
    [422, "invalid_question"],
    [429, "limit_reached"],
    [503, "database_unavailable"],
  ])("maps %i to the %s failure", async (status, failure) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(failingResponse(status)));

    await expect(collect(ask())).rejects.toMatchObject({ failure });
  });

  it("degrades an unmapped status to unreachable rather than leaking it", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(failingResponse(500)));

    await expect(collect(ask())).rejects.toMatchObject({ failure: "unreachable" });
  });

  it("treats a network failure as unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    await expect(collect(ask())).rejects.toBeInstanceOf(ChatRequestError);
  });

  it("treats a 200 with no body as unreachable instead of an empty answer", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, body: null }));

    await expect(collect(ask())).rejects.toMatchObject({ failure: "unreachable" });
  });

  it("never reads the error body, which may name the provider or the prompt", async () => {
    // The T-63 safety rule and the T-52 attack surface: whatever a failing
    // backend puts in the body must not reach the caller at all.
    const text = vi.fn().mockResolvedValue("upstream provider Foo rejected the system prompt");
    const json = vi.fn().mockResolvedValue({ detail: "provider Foo" });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(failingResponse(503, { text, json })));

    const error = await collect(ask()).catch((caught: unknown) => caught);

    expect(text).not.toHaveBeenCalled();
    expect(json).not.toHaveBeenCalled();
    expect((error as Error).message).not.toContain("Foo");
  });

  it("rethrows an abort as-is so a cancelled request is not reported as a fault", async () => {
    const aborted = new Error("aborted");
    aborted.name = "AbortError";
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(aborted));

    await expect(collect(ask())).rejects.toBe(aborted);
  });
});
