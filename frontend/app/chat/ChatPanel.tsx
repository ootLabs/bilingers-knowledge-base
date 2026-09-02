"use client";

import { useEffect, useRef, useState } from "react";

import StatusMessage from "@/components/StatusMessage";
import {
  ChatRequestError,
  type ChatFailure,
  createSessionToken,
  streamAnswer,
} from "@/lib/api-client";
import { getTranslations } from "@/lib/i18n";

import TypingIndicator from "./TypingIndicator";

// The question box exists here only so the four states T-63 owns are
// reachable by a real parent rather than by a test harness. The conversation
// proper - history, the follow-up threads prof. Magdalena asked for, the
// self-description and suggested openers from T-61 - is T-62, which this
// card blocks. Resist growing it here.

type PanelState =
  | { phase: "empty" }
  | { phase: "waiting" }
  | { phase: "answering"; answer: string }
  | { phase: "answered"; answer: string }
  | { phase: "failed"; failure: ChatFailure };

// The limit is a conversion point, not a fault (T-61: "ekran limitu to NIE
// jest komunikat bledu"), so it gets its own tone and sends the parent
// onward instead of offering a pointless retry.
const TONE_BY_FAILURE: Record<ChatFailure, "error" | "limit"> = {
  invalid_question: "error",
  limit_reached: "limit",
  database_unavailable: "error",
  unreachable: "error",
};

export default function ChatPanel() {
  const t = getTranslations();
  const [question, setQuestion] = useState("");
  const [state, setState] = useState<PanelState>({ phase: "empty" });

  // Minted on first use rather than at module scope: `crypto.randomUUID`
  // would otherwise run during prerender and hand every visitor the same
  // conversation.
  const sessionToken = useRef<string | null>(null);
  const inFlight = useRef<AbortController | null>(null);
  // The question the current answer belongs to, so retry re-sends what was
  // actually asked even if the box has been edited since.
  const askedQuestion = useRef("");

  useEffect(() => {
    return () => inFlight.current?.abort();
  }, []);

  async function ask(asked: string) {
    inFlight.current?.abort();
    const controller = new AbortController();
    inFlight.current = controller;
    askedQuestion.current = asked;

    // Set before the first await so the indicator is painted on submit, not
    // on first byte (acceptance criterion 1).
    setState({ phase: "waiting" });

    let answer = "";
    let pending = "";
    try {
      // Inside the try: minting the token can throw (see `createSessionToken`),
      // and a throw before it would leave the click with no visible outcome at
      // all rather than a failure state.
      sessionToken.current ??= createSessionToken();

      for await (const chunk of streamAnswer({
        question: asked,
        sessionToken: sessionToken.current,
        signal: controller.signal,
      })) {
        pending += chunk;
        // The backend streams one translation key per line, never prose
        // (see `stream_placeholder_answer`), and a chunk boundary can fall
        // mid-key, so only whole lines are resolved. The remainder waits.
        const lines = pending.split("\n");
        pending = lines.pop() ?? "";
        for (const line of lines) {
          answer += resolveChunk(t, line);
        }
        // Only once there is something to read. A chunk that carries no
        // complete line yet (or only unresolvable keys) must leave the typing
        // indicator up: swapping it for an empty answer box would drop the
        // loading state while the request is still running.
        if (answer !== "") {
          setState({ phase: "answering", answer });
        }
      }
      answer += resolveChunk(t, pending);
      if (answer === "") {
        // The stream ended without a single resolvable key, so there is
        // nothing to show. Same call as `streamAnswer` makes for a 200 with
        // no body: a blank reply must not be presented as the answer.
        setState({ phase: "failed", failure: "unreachable" });
        return;
      }
      setState({ phase: "answered", answer });
    } catch (error) {
      if (controller.signal.aborted) {
        return;
      }
      // Anything that is not a mapped failure is still shown as one: an
      // unexpected error must not fall through to a raw message on screen.
      setState({
        phase: "failed",
        failure: error instanceof ChatRequestError ? error.failure : "unreachable",
      });
    } finally {
      if (inFlight.current === controller) {
        inFlight.current = null;
      }
    }
  }

  const busy = state.phase === "waiting" || state.phase === "answering";
  const trimmed = question.trim();

  return (
    <div className="chat-panel">
      <form
        className="chat-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (trimmed !== "" && !busy) {
            void ask(trimmed);
          }
        }}
      >
        <label className="chat-form__label" htmlFor="chat-question">
          {t("chat.inputLabel")}
        </label>
        <textarea
          id="chat-question"
          className="chat-form__input"
          rows={3}
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder={t("chat.inputPlaceholder")}
        />
        <button type="submit" className="cta-button" disabled={trimmed === "" || busy}>
          {t("chat.submit")}
        </button>
      </form>

      {/* One region for every state, with its height reserved in CSS, so
          moving between them never reflows the form above (acceptance
          criterion 3). `polite` rather than `assertive`: an answer arriving
          should not cut off whatever a screen reader is mid-sentence on. */}
      <div className="chat-status" aria-live="polite">
        {state.phase === "empty" && (
          <StatusMessage
            tone="info"
            titleKey="chat.empty.title"
            descriptionKey="chat.empty.description"
          />
        )}
        {state.phase === "waiting" && <TypingIndicator />}
        {(state.phase === "answering" || state.phase === "answered") && (
          <article className="chat-answer">
            <h2 className="chat-answer__label">{t("chat.answerLabel")}</h2>
            <p className="chat-answer__body">{state.answer}</p>
          </article>
        )}
        {state.phase === "failed" && (
          <StatusMessage
            tone={TONE_BY_FAILURE[state.failure]}
            titleKey={`errors.${state.failure}.title`}
            descriptionKey={`errors.${state.failure}.description`}
            action={
              state.failure === "limit_reached"
                ? { kind: "link", labelKey: "errors.limit_reached.action", href: "/account" }
                : {
                    kind: "retry",
                    labelKey: "errors.retry",
                    onRetry: () => void ask(askedQuestion.current),
                  }
            }
          />
        )}
      </div>
    </div>
  );
}

/**
 * Turn one streamed line into displayable copy.
 *
 * A key the dictionary does not know comes back from `t` unchanged, which on
 * screen would read as a technical identifier - the exact thing T-63 forbids
 * showing a parent. Such a line is dropped instead.
 */
function resolveChunk(t: (key: string) => string, line: string): string {
  const key = line.trim();
  if (key === "") {
    return "";
  }
  const resolved = t(key);
  return resolved === key ? "" : resolved;
}
