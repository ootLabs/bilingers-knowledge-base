// The single place the browser talks to the backend. Components never call
// fetch directly (see docs/map/frontend.md), because every failure has to be
// funnelled through the small vocabulary of `ChatFailure` below before any
// copy layer sees it.

// Exported so the landing page can show the value the client will actually
// use. Two copies of this fallback would let the diagnostic on `/` advertise
// a backend the requests never go to.
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Mirrors the backend's `detail` keys plus the two cases the backend cannot
// report about itself (unreachable, and a quota that nothing enforces yet).
// Deliberately a closed union: a status the backend starts returning that is
// not listed here degrades to "unreachable" instead of reaching the user as
// an unhandled shape.
export type ChatFailure =
  | "invalid_question"
  | "limit_reached"
  | "database_unavailable"
  | "unreachable";

// 429 is wired up before anything emits it. The anonymous quota from D5 is
// T-71/T-73's job; T-63 only owns what the parent sees when it trips, and a
// state nobody can reach is a state nobody has tested. Mapping the standard
// status now means the counter lands without touching this file.
const FAILURE_BY_STATUS: Record<number, ChatFailure> = {
  422: "invalid_question",
  429: "limit_reached",
  503: "database_unavailable",
};

/** A failed `/chat` call, reduced to a key the copy layer can translate. */
export class ChatRequestError extends Error {
  readonly failure: ChatFailure;

  constructor(failure: ChatFailure) {
    // The message is for a developer reading a stack trace, never for the
    // screen: `ChatPanel` renders copy keyed by `failure` and ignores this.
    super(`chat request failed: ${failure}`);
    this.name = "ChatRequestError";
    this.failure = failure;
  }
}

/**
 * Mint a conversation token.
 *
 * Must satisfy the backend's `^[0-9a-f]{32,64}$` (see
 * `backend/app/schemas/chat.py`). A token that fails that pattern comes back
 * as a 422 on every single question, which reads like a broken question
 * rather than a broken token.
 *
 * Built from `getRandomValues` rather than `randomUUID`, which is exposed
 * only in a secure context: served over plain http from anything but
 * localhost (a LAN address during a demo, an http staging host) it is
 * `undefined`, and the call would throw where the caller expects a token.
 * `getRandomValues` carries no such restriction.
 */
export function createSessionToken(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

/**
 * Post one question and yield the answer as it arrives.
 *
 * Yields whatever the backend sends, which today is one translation key per
 * line rather than prose (see `stream_placeholder_answer`); resolving those
 * to Polish is the caller's job, not this layer's.
 *
 * The error body is never read, on purpose. Whatever a failing backend puts
 * in it may name the model provider or quote the system prompt, and the
 * moment it is in hand something will eventually render it (T-52, and the
 * safety rule on T-63). The status code is the only thing taken from a
 * failed response.
 */
export async function* streamAnswer({
  question,
  sessionToken,
  signal,
}: {
  question: string;
  sessionToken: string;
  signal?: AbortSignal;
}): AsyncGenerator<string> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, session_token: sessionToken }),
      signal,
    });
  } catch (error) {
    // An abort is the caller changing its mind, not a fault to report.
    if (error instanceof Error && error.name === "AbortError") {
      throw error;
    }
    throw new ChatRequestError("unreachable");
  }

  if (!response.ok) {
    throw new ChatRequestError(FAILURE_BY_STATUS[response.status] ?? "unreachable");
  }

  // A 200 with no body is not a real answer, and treating it as an empty
  // one would show the parent a blank reply as though it were the response.
  if (response.body === null) {
    throw new ChatRequestError("unreachable");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      // `stream: true` so a multi-byte character split across two chunks is
      // held back rather than decoded into a replacement character. Polish
      // copy is full of them.
      const text = decoder.decode(value, { stream: true });
      if (text !== "") {
        yield text;
      }
    }
    const tail = decoder.decode();
    if (tail !== "") {
      yield tail;
    }
  } finally {
    // Not `releaseLock` alone: leaving the loop early - the caller breaks out
    // of its `for await`, or throws inside it - would otherwise leave the
    // response body open on a connection nobody reads any more. An abort
    // already tears the body down; this covers every other way out.
    await reader.cancel();
    reader.releaseLock();
  }
}
