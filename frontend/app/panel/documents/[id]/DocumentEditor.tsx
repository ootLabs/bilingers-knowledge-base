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
  saveVersion,
  type DocumentDetail,
  type VersionDetail,
  type VersionSummary,
} from "@/lib/panel-documents";

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
  // `live` is whichever version parents are reading, which is not the one
  // being edited as soon as anybody saves. Without it this screen said
  // nothing at all about a document it was actively serving.
  | { phase: "ready"; base: VersionDetail; live: VersionSummary | null };

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

  /**
   * Re-read what the screen says about the document, and nothing else.
   *
   * `draft` is deliberately untouched. The text in the box may be work the
   * editor has typed and not saved, and it is then the only copy of it, which
   * is the same reason `submit` leaves it alone when a save is refused.
   * Publishing acts on the last saved version and has no business overwriting
   * the box.
   */
  const refresh = useCallback(async (signal?: AbortSignal): Promise<DocumentDetail | null> => {
    try {
      const document = await getDocument(documentId, signal);
      setState({
        phase: "ready",
        base: document.latestVersion,
        live: document.publishedVersion,
      });
      return document;
    } catch (error) {
      const failure = recover(error);
      if (failure !== null) {
        setState({ phase: "failed", failure });
      }
      return null;
    }
  }, [documentId, recover]);

  // Opening the document: the same read, plus seeding the form from it. Seeding
  // happens only here, because this is the one moment when there is no typed
  // text that could be lost.
  const load = useCallback(async (signal?: AbortSignal) => {
    setState({ phase: "loading" });
    const document = await refresh(signal);
    if (document !== null) {
      setDraft(draftFrom(document.latestVersion));
    }
  }, [refresh]);

  useEffect(() => {
    // `documentId` comes from the route, so this callback changes when the
    // editor moves to another document. Without the abort, the first
    // document's answer could arrive after the second's and seed the form with
    // the wrong text.
    const request = new AbortController();
    void load(request.signal);
    return () => request.abort();
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
      // The published version is untouched by a save, by design: that is the
      // whole point of a save never changing what a parent reads.
      setState({ phase: "ready", base: version, live: state.live });
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
  const live = state.live;

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
        {base.status === "published" ? (
          // The one confusion worth a whole block of its own: editing on top of
          // what parents are reading right now.
          <p className="editor-context__warning">{t("panel.editor.editingPublished")}</p>
        ) : live !== null ? (
          // Editing a draft while a different version is live. Silence here
          // was the bug: the screen looked identical whether the document was
          // being served or had never been published.
          <p className="editor-context__warning">
            {fill(t("panel.editor.parentsReadOther"), { version: live.versionNumber })}
          </p>
        ) : (
          <p className="editor-context__line editor-context__line--muted">
            {t("panel.editor.nothingPublished")}
          </p>
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
        live={live}
        onChanged={() => {
          // Publishing or withdrawing changes both answers at once (which
          // version is live, and what the newest one's status is), so the
          // document is re-read rather than patched here from one half of it.
          // `refresh`, not `load`: whatever is typed in the box stays.
          setSavedAs(null);
          void refresh();
        }}
      />
    </>
  );
}
