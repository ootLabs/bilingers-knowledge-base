"use client";

import { useState } from "react";

import StatusMessage from "@/components/StatusMessage";
import { formatDateTime } from "@/lib/format-date";
import { fill, getTranslations } from "@/lib/i18n";
import type { PanelFailure } from "@/lib/panel-client";
import { publishVersion, type VersionDetail, withdrawVersion } from "@/lib/panel-documents";

import { useSessionRecovery } from "../../use-session-recovery";

// Publishing is the moment the panel stops being a CMS with no consequences,
// so the screen says so in plain words rather than in a status code: what state
// the version is in, since when, and who put it there.
//
// Silence after a click is what makes an editor click a second time, so every
// outcome writes a sentence, including "nothing changed, it was already
// published".

export default function PublicationControls({
  documentId,
  version,
  onChanged,
}: {
  documentId: number;
  version: VersionDetail;
  onChanged: (version: VersionDetail) => void;
}) {
  const t = getTranslations();
  const recover = useSessionRecovery();
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<PanelFailure | null>(null);

  const published = version.status === "published";

  async function run(action: () => Promise<VersionDetail>) {
    if (busy) {
      return;
    }
    setBusy(true);
    setFailure(null);
    try {
      onChanged(await action());
    } catch (error) {
      setFailure(recover(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="publication">
      <h2 className="publication__heading">{t("panel.publish.heading")}</h2>

      <p className="publication__state">
        {published ? t("panel.publish.isPublished") : t("panel.publish.isNotPublished")}
      </p>

      {published && version.publishedAt !== null && (
        <p className="publication__meta">
          {fill(t("panel.publish.publishedOn"), {
            date: formatDateTime(version.publishedAt),
            author: version.publishedByEmail ?? t("panel.publish.unknownPublisher"),
          })}
        </p>
      )}

      <div className="publication__actions">
        {published ? (
          <button
            type="button"
            className="cta-button"
            disabled={busy}
            onClick={() => void run(() => withdrawVersion(documentId, version.versionNumber))}
          >
            {busy ? t("panel.publish.working") : t("panel.publish.withdraw")}
          </button>
        ) : (
          <button
            type="button"
            className="cta-button"
            disabled={busy}
            onClick={() => void run(() => publishVersion(documentId, version.versionNumber))}
          >
            {busy ? t("panel.publish.working") : t("panel.publish.publish")}
          </button>
        )}
      </div>

      <div aria-live="polite">
        {failure !== null && (
          <StatusMessage
            tone="error"
            titleKey={`panel.errors.${failure}.title`}
            descriptionKey={`panel.errors.${failure}.description`}
          />
        )}
      </div>
    </section>
  );
}
