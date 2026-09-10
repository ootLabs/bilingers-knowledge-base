"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import StatusMessage from "@/components/StatusMessage";
import StatusPill from "@/components/StatusPill";
import { formatDateTime } from "@/lib/format-date";
import { fill, getTranslations } from "@/lib/i18n";
import type { PanelFailure } from "@/lib/panel-client";
import {
  getDocument,
  getVersion,
  listVersions,
  restoreVersion,
  type VersionDetail,
  type VersionSummary,
} from "@/lib/panel-documents";
import { diffLines } from "@/lib/text-diff";

import { useSessionRecovery } from "../../../use-session-recovery";

// What changed, when, and by whom, plus the way back. Restoring copies an old
// version forward as a new one, so the list only ever gets longer: what was
// undone stays readable, which is the whole reason this model was chosen.

type HistoryState =
  | { phase: "loading" }
  | { phase: "failed"; failure: PanelFailure }
  | { phase: "ready"; versions: VersionSummary[]; current: VersionDetail };

export default function VersionHistory({ documentId }: { documentId: number }) {
  const t = getTranslations();
  const recover = useSessionRecovery();
  const [state, setState] = useState<HistoryState>({ phase: "loading" });
  const [selected, setSelected] = useState<VersionDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<PanelFailure | null>(null);
  const [restoredAs, setRestoredAs] = useState<number | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    setState({ phase: "loading" });
    try {
      const [versions, document] = await Promise.all([
        listVersions(documentId, signal),
        getDocument(documentId, signal),
      ]);
      setState({ phase: "ready", versions, current: document.latestVersion });
    } catch (error) {
      const recovered = recover(error);
      if (recovered !== null) {
        setState({ phase: "failed", failure: recovered });
      }
    }
  }, [documentId, recover]);

  useEffect(() => {
    const request = new AbortController();
    void load(request.signal);
    return () => request.abort();
  }, [load]);

  async function preview(versionNumber: number) {
    setBusy(true);
    setFailure(null);
    try {
      setSelected(await getVersion(documentId, versionNumber));
    } catch (error) {
      setFailure(recover(error));
    } finally {
      setBusy(false);
    }
  }

  async function restore(versionNumber: number) {
    setBusy(true);
    setFailure(null);
    setRestoredAs(null);
    try {
      // The note is written here, not in the backend: it is a Polish sentence,
      // and Polish sentences live in the dictionary (docs/conventions.md).
      const created = await restoreVersion(
        documentId,
        versionNumber,
        fill(t("panel.history.restoreComment"), { version: versionNumber }),
      );
      setRestoredAs(created.versionNumber);
      setSelected(null);
      await load();
    } catch (error) {
      setFailure(recover(error));
    } finally {
      setBusy(false);
    }
  }

  if (state.phase === "loading") {
    return (
      <StatusMessage
        tone="info"
        titleKey="panel.history.loading.title"
        descriptionKey="panel.history.loading.description"
      />
    );
  }

  if (state.phase === "failed") {
    return (
      <StatusMessage
        tone="error"
        titleKey={`panel.errors.${state.failure}.title`}
        descriptionKey={`panel.errors.${state.failure}.description`}
        action={{ kind: "retry", labelKey: "panel.errors.retry", onRetry: () => void load() }}
      />
    );
  }

  return (
    <>
      <p className="panel-breadcrumb">
        <Link href={`/panel/documents/${documentId}`}>{t("panel.history.backToEditor")}</Link>
      </p>

      <div aria-live="polite">
        {restoredAs !== null && (
          <p className="editor-saved">
            {fill(t("panel.history.restored"), { version: restoredAs })}
          </p>
        )}
        {failure !== null && (
          <StatusMessage
            tone="error"
            titleKey={`panel.errors.${failure}.title`}
            descriptionKey={`panel.errors.${failure}.description`}
          />
        )}
      </div>

      <ol className="version-list">
        {state.versions.map((version) => (
          <li key={version.versionNumber} className="version-row">
            <div className="version-row__heading">
              <strong>{fill(t("panel.history.versionLabel"), { version: version.versionNumber })}</strong>
              <StatusPill status={version.status} />
              {version.versionNumber === state.current.versionNumber && (
                <span className="version-row__current">{t("panel.history.currentMarker")}</span>
              )}
            </div>
            <p className="version-row__meta">
              {formatDateTime(version.createdAt)}
              {version.authorEmail !== null && `, ${version.authorEmail}`}
            </p>
            {version.changeComment !== null && (
              <p className="version-row__comment">{version.changeComment}</p>
            )}
            <p className="version-row__actions">
              <button
                type="button"
                className="link-button"
                disabled={busy}
                onClick={() => void preview(version.versionNumber)}
              >
                {t("panel.history.preview")}
              </button>
              {version.versionNumber !== state.current.versionNumber && (
                <button
                  type="button"
                  className="link-button"
                  disabled={busy}
                  onClick={() => void restore(version.versionNumber)}
                >
                  {t("panel.history.restore")}
                </button>
              )}
            </p>
          </li>
        ))}
      </ol>

      {selected !== null && (
        <section className="version-preview">
          <h2>
            {fill(t("panel.history.comparingHeading"), {
              version: selected.versionNumber,
              current: state.current.versionNumber,
            })}
          </h2>
          <p className="panel-field__hint">{t("panel.history.comparingHint")}</p>
          <ol className="diff">
            {diffLines(selected.content, state.current.content).map((line, index) => (
              <li key={`${index}-${line.kind}`} className={`diff__line diff__line--${line.kind}`}>
                {/* The marker column is decorative; the word next to it is what
                    a screen reader announces, because a colored bar and a "+"
                    are not a signal on their own. */}
                <span className="diff__marker" aria-hidden="true">
                  {line.kind === "added" ? "+" : line.kind === "removed" ? "-" : " "}
                </span>
                {line.kind !== "same" && (
                  <span className="visually-hidden">{t(`panel.history.diff.${line.kind}`)} </span>
                )}
                <span className="diff__text">{line.text}</span>
              </li>
            ))}
          </ol>
        </section>
      )}
    </>
  );
}
