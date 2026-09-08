"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import StatusMessage from "@/components/StatusMessage";
import StatusPill from "@/components/StatusPill";
import { formatDateTime } from "@/lib/format-date";
import { fill, getTranslations } from "@/lib/i18n";
import type { PanelFailure } from "@/lib/panel-client";
import { getDocument, saveVersion, type VersionDetail } from "@/lib/panel-documents";

import DocumentForm, { type DocumentDraft } from "../DocumentForm";
import PublicationControls from "./PublicationControls";
import { useSessionRecovery } from "../../use-session-recovery";

// Where the foundation actually grows the knowledge base. Three things have to
// be unmistakable on this screen, because getting any of them wrong is a change
// made to what parents read without anyone realising:
//
//   1. whether the text on screen is a draft or the published version,
//   2. which version number and date it came from, so it is visible that this
//      is not somebody else's save from a minute ago,
//   3. what happened after saving, in a sentence, not as a spinner stopping.
//
// There is no autosave. An explicit save is what makes "I changed this on
// purpose" true, and autosave into a versioned store would mint a version per
// keystroke pause. It comes back as its own card if the editors ask for it.

type EditorState =
  | { phase: "loading" }
  | { phase: "failed"; failure: PanelFailure }
  | { phase: "ready"; base: VersionDetail };

function draftFrom(version: VersionDetail): DocumentDraft {
  return { title: version.title, content: version.content, changeComment: "" };
}

export default function DocumentEditor({ documentId }: { documentId: number }) {
  const t = getTranslations();
  const recover = useSessionRecovery();
  const [state, setState] = useState<EditorState>({ phase: "loading" });
  const [draft, setDraft] = useState<DocumentDraft>({
    title: "",
    content: "",
    changeComment: "",
  });
  const [saving, setSaving] = useState(false);
  const [saveFailure, setSaveFailure] = useState<PanelFailure | null>(null);
  const [savedAs, setSavedAs] = useState<VersionDetail | null>(null);

  const load = useCallback(async () => {
    setState({ phase: "loading" });
    try {
      const document = await getDocument(documentId);
      setState({ phase: "ready", base: document.latestVersion });
      setDraft(draftFrom(document.latestVersion));
    } catch (error) {
      const failure = recover(error);
      if (failure !== null) {
        setState({ phase: "failed", failure });
      }
    }
  }, [documentId, recover]);

  useEffect(() => {
    void load();
  }, [load]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (state.phase !== "ready" || saving || draft.title.trim() === "") {
      return;
    }
    setSaving(true);
    setSaveFailure(null);
    setSavedAs(null);
    try {
      const version = await saveVersion(documentId, {
        title: draft.title.trim(),
        content: draft.content,
        changeComment: draft.changeComment.trim() || null,
      });
      setState({ phase: "ready", base: version });
      // The comment belonged to the save that just happened; carrying it into
      // the next one would file the wrong note against the wrong change.
      setDraft({ ...draft, changeComment: "" });
      setSavedAs(version);
    } catch (error) {
      // Nothing touches `draft` here. A rejected save must leave the text
      // exactly where it is: on a 409 it is the only copy that exists.
      setSaveFailure(recover(error));
    } finally {
      setSaving(false);
    }
  }

  if (state.phase === "loading") {
    return (
      <StatusMessage
        tone="info"
        titleKey="panel.editor.loading.title"
        descriptionKey="panel.editor.loading.description"
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

  const base = state.base;

  return (
    <>
      <div className="editor-context">
        <p className="editor-context__line">
          <StatusPill status={base.status} />{" "}
          {fill(t("panel.editor.editing"), {
            version: base.versionNumber,
            date: formatDateTime(base.createdAt),
          })}
        </p>
        {base.authorEmail !== null && (
          <p className="editor-context__line editor-context__line--muted">
            {fill(t("panel.editor.lastSavedBy"), { author: base.authorEmail })}
          </p>
        )}
        {base.status === "published" && (
          // The one confusion worth a whole block of its own: editing on top of
          // what parents are reading right now.
          <p className="editor-context__warning">{t("panel.editor.editingPublished")}</p>
        )}
        <p className="editor-context__links">
          <Link href="/panel/documents">{t("panel.editor.backToList")}</Link>
          <Link href={`/panel/documents/${documentId}/history`}>
            {t("panel.editor.openHistory")}
          </Link>
        </p>
      </div>

      <form className="panel-form panel-form--wide" onSubmit={submit}>
        <DocumentForm draft={draft} onChange={setDraft} disabled={saving} />

        <button
          type="submit"
          className="cta-button"
          disabled={saving || draft.title.trim() === ""}
        >
          {saving ? t("panel.editor.saving") : t("panel.editor.saveSubmit")}
        </button>

        {/* What happened, in words. Silence after a click is what makes an
            editor click a second time and wonder whether she saved twice. */}
        <div className="panel-form__status" aria-live="polite">
          {savedAs !== null && (
            <p className="editor-saved">
              {fill(t("panel.editor.saved"), { version: savedAs.versionNumber })}
            </p>
          )}
          {saveFailure !== null && (
            <StatusMessage
              tone="error"
              titleKey={`panel.errors.${saveFailure}.title`}
              descriptionKey={`panel.errors.${saveFailure}.description`}
            />
          )}
        </div>
      </form>

      {/* Below the editor, not beside the save button: publishing and saving
          are different decisions, and putting them side by side is how one gets
          clicked in place of the other. */}
      <PublicationControls
        documentId={documentId}
        version={base}
        onChanged={(version) => {
          setState({ phase: "ready", base: version });
          setSavedAs(null);
        }}
      />
    </>
  );
}
