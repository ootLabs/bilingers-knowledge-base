"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import StatusMessage from "@/components/StatusMessage";
import { getTranslations } from "@/lib/i18n";
import type { PanelFailure } from "@/lib/panel-client";
import { createDocument } from "@/lib/panel-documents";

import DocumentForm, { type DocumentDraft } from "../DocumentForm";
import { useSessionRecovery } from "../../use-session-recovery";

// A new document, saved as version 1 in the draft state. Nothing here can
// publish, so writing a first draft can never change what a parent is reading.

const EMPTY: DocumentDraft = { title: "", content: "", changeComment: "" };

export default function NewDocumentForm() {
  const t = getTranslations();
  const router = useRouter();
  const recover = useSessionRecovery();
  const [draft, setDraft] = useState<DocumentDraft>(EMPTY);
  const [saving, setSaving] = useState(false);
  const [failure, setFailure] = useState<PanelFailure | null>(null);

  const complete = draft.title.trim() !== "" && draft.content.trim() !== "";

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!complete || saving) {
      return;
    }
    setSaving(true);
    setFailure(null);
    try {
      const created = await createDocument({
        title: draft.title.trim(),
        content: draft.content,
        changeComment: draft.changeComment.trim() || null,
      });
      // Straight into the editor for the document just created, so the next
      // thing on screen is the thing that was written, with its version number
      // and its state on it.
      router.replace(`/panel/documents/${created.id}`);
    } catch (error) {
      // The typed text is never cleared on a failure. It is the only copy.
      setFailure(recover(error));
      setSaving(false);
    }
  }

  return (
    <form className="panel-form panel-form--wide" onSubmit={submit}>
      <DocumentForm draft={draft} onChange={setDraft} disabled={saving} />

      <button type="submit" className="cta-button" disabled={!complete || saving}>
        {saving ? t("panel.editor.saving") : t("panel.editor.createSubmit")}
      </button>

      <div className="panel-form__status" aria-live="polite">
        {failure !== null && (
          <StatusMessage
            tone="error"
            titleKey={`panel.errors.${failure}.title`}
            descriptionKey={`panel.errors.${failure}.description`}
          />
        )}
      </div>
    </form>
  );
}
