"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import StatusMessage from "@/components/StatusMessage";
import { fill, getTranslations } from "@/lib/i18n";
import type { PanelFailure } from "@/lib/panel-client";
import {
  createDocument,
  type DocumentSummary,
  listDocuments,
  saveVersion,
} from "@/lib/panel-documents";
import { type ImportPreview, previewImport } from "@/lib/panel-imports";

import { useSessionRecovery } from "../../use-session-recovery";

// Two steps on purpose. Reading the file writes nothing, and what it understood
// is put in front of the editor before any of it exists: a file the reader got
// wrong has to be refused by a person, not discovered as a draft months later.
//
// Importing into an existing document is a normal save, so it becomes that
// document's next version rather than a second copy of it under a similar name.

const NEW_DOCUMENT = "new";

export default function DocumentImport() {
  const t = getTranslations();
  const router = useRouter();
  const recover = useSessionRecovery();
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [title, setTitle] = useState("");
  const [target, setTarget] = useState<string>(NEW_DOCUMENT);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<PanelFailure | null>(null);

  useEffect(() => {
    // Only to offer "add to an existing document". A failure here is not worth
    // a screen of its own: the import still works, it just cannot offer that.
    listDocuments()
      .then(setDocuments)
      .catch(() => setDocuments([]));
  }, []);

  async function read(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const input = event.currentTarget.elements.namedItem("docx") as HTMLInputElement | null;
    const file = input?.files?.[0];
    if (!file || busy) {
      return;
    }
    setBusy(true);
    setFailure(null);
    try {
      const result = await previewImport(file);
      setPreview(result);
      setTitle(result.title);
    } catch (error) {
      setPreview(null);
      setFailure(recover(error));
    } finally {
      setBusy(false);
    }
  }

  async function accept() {
    if (preview === null || busy || title.trim() === "") {
      return;
    }
    setBusy(true);
    setFailure(null);
    try {
      const content = {
        title: title.trim(),
        content: preview.content,
        changeComment: t("panel.import.changeComment"),
      };
      if (target === NEW_DOCUMENT) {
        const created = await createDocument(content);
        router.replace(`/panel/documents/${created.id}`);
        return;
      }
      await saveVersion(Number(target), content);
      router.replace(`/panel/documents/${target}`);
    } catch (error) {
      setFailure(recover(error));
      setBusy(false);
    }
  }

  return (
    <>
      <p className="panel-breadcrumb">
        <Link href="/panel/documents">{t("panel.editor.backToList")}</Link>
      </p>

      <form className="panel-form" onSubmit={read}>
        <div className="panel-field">
          <label className="panel-field__label" htmlFor="docx">
            {t("panel.import.fileLabel")}
          </label>
          <input id="docx" name="docx" className="panel-field__input" type="file" accept=".docx" />
          <p className="panel-field__hint">{t("panel.import.fileHint")}</p>
        </div>
        <button type="submit" className="cta-button" disabled={busy}>
          {busy ? t("panel.import.reading") : t("panel.import.read")}
        </button>
      </form>

      <div className="panel-form__status" aria-live="polite">
        {failure !== null && (
          <StatusMessage
            tone="error"
            titleKey={`panel.errors.${failure}.title`}
            descriptionKey={`panel.errors.${failure}.description`}
          />
        )}
      </div>

      {preview !== null && (
        <section className="import-preview">
          <h2>{t("panel.import.previewHeading")}</h2>
          <p>
            {fill(t("panel.import.report"), {
              headings: preview.headingCount,
              paragraphs: preview.paragraphCount,
            })}
          </p>
          {preview.skipped.length > 0 ? (
            <ul className="import-skipped">
              {preview.skipped.map((item) => (
                <li key={item.reason}>
                  {fill(t(`panel.import.skipped.${item.reason}`), { count: item.count })}
                </li>
              ))}
            </ul>
          ) : (
            <p className="panel-field__hint">{t("panel.import.nothingSkipped")}</p>
          )}

          <div className="panel-field">
            <label className="panel-field__label" htmlFor="import-title">
              {t("panel.import.titleLabel")}
            </label>
            <input
              id="import-title"
              className="panel-field__input"
              type="text"
              maxLength={500}
              value={title}
              onChange={(event) => setTitle(event.target.value)}
            />
          </div>

          <div className="panel-field">
            <label className="panel-field__label" htmlFor="import-target">
              {t("panel.import.targetLabel")}
            </label>
            <select
              id="import-target"
              className="panel-field__input"
              value={target}
              onChange={(event) => setTarget(event.target.value)}
            >
              <option value={NEW_DOCUMENT}>{t("panel.import.targetNew")}</option>
              {documents.map((document) => (
                <option key={document.id} value={String(document.id)}>
                  {document.latestVersion.title}
                </option>
              ))}
            </select>
            <p className="panel-field__hint">{t("panel.import.targetHint")}</p>
          </div>

          <h3>{t("panel.import.contentHeading")}</h3>
          <pre className="import-content">{preview.content}</pre>

          <div className="import-decision">
            <button
              type="button"
              className="cta-button"
              disabled={busy || title.trim() === ""}
              onClick={() => void accept()}
            >
              {t("panel.import.accept")}
            </button>
            <button
              type="button"
              className="link-button"
              disabled={busy}
              onClick={() => setPreview(null)}
            >
              {t("panel.import.reject")}
            </button>
          </div>
        </section>
      )}
    </>
  );
}
