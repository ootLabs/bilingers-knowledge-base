"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import StatusMessage from "@/components/StatusMessage";
import { formatDateTime } from "@/lib/format-date";
import { getTranslations } from "@/lib/i18n";
import { type AuditEntry, listAuditEvents } from "@/lib/panel-audit";
import type { PanelFailure } from "@/lib/panel-client";

import { useSessionRecovery } from "../use-session-recovery";

// Read only, and it looks it: no row is clickable, nothing here edits anything.
// The screen exists so the foundation can answer "who had access to the base
// and what did they do with it", which is a different question from "how did
// the text change" (that is the version history).

type LogState =
  | { phase: "loading" }
  | { phase: "failed"; failure: PanelFailure }
  | { phase: "ready"; entries: AuditEntry[] };

export default function AuditLog() {
  const t = getTranslations();
  const recover = useSessionRecovery();
  const [state, setState] = useState<LogState>({ phase: "loading" });
  const [actorEmail, setActorEmail] = useState("");
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");

  // The read still in the air, if any, so leaving the screen does not leave a
  // request answering into nothing.
  //
  // Two clicks on "Pokaż" used to be one gesture apart, and the older answer
  // could land second with entries that did not match the filters above them.
  // That is closed at the source now: the button is disabled while a read runs,
  // the way publish and save are. This covers what disabling cannot.
  const inFlight = useRef<AbortController | null>(null);

  const load = useCallback(
    async (filters: { actorEmail: string; since: string; until: string }) => {
      inFlight.current?.abort();
      const request = new AbortController();
      inFlight.current = request;
      setState({ phase: "loading" });
      try {
        setState({ phase: "ready", entries: await listAuditEvents(filters, request.signal) });
      } catch (error) {
        // An abort comes back as null: it is this screen cancelling itself, so
        // there is nothing to render and the newer read owns the state.
        const failure = recover(error);
        if (failure !== null) {
          setState({ phase: "failed", failure });
        }
      }
    },
    [recover],
  );

  useEffect(() => {
    void load({ actorEmail: "", since: "", until: "" });
    return () => inFlight.current?.abort();
  }, [load]);

  function describe(entry: AuditEntry): string {
    // An unknown action prints its own key rather than nothing: a blank line in
    // a journal is worse than a technical word in one, because it hides that
    // something happened at all.
    const label = t(`panel.audit.actions.${entry.action}`);
    return label === `panel.audit.actions.${entry.action}` ? entry.action : label;
  }

  return (
    <>
      <form
        className="document-filters"
        onSubmit={(event) => {
          event.preventDefault();
          void load({ actorEmail, since, until });
        }}
      >
        <div className="panel-field">
          <label className="panel-field__label" htmlFor="audit-actor">
            {t("panel.audit.actorLabel")}
          </label>
          <input
            id="audit-actor"
            className="panel-field__input"
            type="text"
            value={actorEmail}
            onChange={(event) => setActorEmail(event.target.value)}
          />
        </div>
        <div className="panel-field">
          <label className="panel-field__label" htmlFor="audit-since">
            {t("panel.audit.sinceLabel")}
          </label>
          <input
            id="audit-since"
            className="panel-field__input"
            type="date"
            value={since}
            onChange={(event) => setSince(event.target.value)}
          />
        </div>
        <div className="panel-field">
          <label className="panel-field__label" htmlFor="audit-until">
            {t("panel.audit.untilLabel")}
          </label>
          <input
            id="audit-until"
            className="panel-field__input"
            type="date"
            value={until}
            onChange={(event) => setUntil(event.target.value)}
          />
        </div>
        <div className="panel-field">
          {/* Not clickable while a read is running, which is how the rest of
              the panel handles this (publish and save both disable). The abort
              above then covers what disabling cannot: leaving the screen, and
              a genuine change of filters. */}
          <button
            type="submit"
            className="cta-button"
            disabled={state.phase === "loading"}
          >
            {state.phase === "loading" ? t("panel.audit.applying") : t("panel.audit.apply")}
          </button>
        </div>
      </form>

      {state.phase === "loading" && (
        <StatusMessage
          tone="info"
          titleKey="panel.audit.loading.title"
          descriptionKey="panel.audit.loading.description"
        />
      )}

      {state.phase === "failed" && (
        <StatusMessage
          tone="error"
          titleKey={`panel.errors.${state.failure}.title`}
          descriptionKey={`panel.errors.${state.failure}.description`}
          action={{
            kind: "retry",
            labelKey: "panel.errors.retry",
            onRetry: () => void load({ actorEmail, since, until }),
          }}
        />
      )}

      {state.phase === "ready" &&
        (state.entries.length === 0 ? (
          <StatusMessage
            tone="info"
            titleKey="panel.audit.empty.title"
            descriptionKey="panel.audit.empty.description"
          />
        ) : (
          <ul className="audit-list">
            {state.entries.map((entry, index) => (
              <li key={`${entry.occurredAt}-${index}`} className="audit-row">
                <p className="audit-row__what">{describe(entry)}</p>
                <p className="audit-row__meta">
                  {formatDateTime(entry.occurredAt)}, {entry.actorEmail}
                  {entry.detail !== null && `, ${entry.detail}`}
                </p>
              </li>
            ))}
          </ul>
        ))}
    </>
  );
}
