"use client";

import { useCallback, useEffect, useState } from "react";

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

  const load = useCallback(
    async (filters: { actorEmail: string; since: string; until: string }) => {
      setState({ phase: "loading" });
      try {
        setState({ phase: "ready", entries: await listAuditEvents(filters) });
      } catch (error) {
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
          <button type="submit" className="cta-button">
            {t("panel.audit.apply")}
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
