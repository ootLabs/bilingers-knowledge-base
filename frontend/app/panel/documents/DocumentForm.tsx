"use client";

import { getTranslations } from "@/lib/i18n";

// The three fields both writing screens share. Fully controlled by whichever
// screen mounts it: after a rejected save the text has to still be on screen,
// and it only can be if the value lives above this component rather than in it.

export type DocumentDraft = {
  title: string;
  content: string;
  changeComment: string;
};

export default function DocumentForm({
  draft,
  onChange,
  disabled = false,
}: {
  draft: DocumentDraft;
  onChange: (draft: DocumentDraft) => void;
  disabled?: boolean;
}) {
  const t = getTranslations();

  return (
    <>
      <div className="panel-field">
        <label className="panel-field__label" htmlFor="document-title">
          {t("panel.editor.titleLabel")}
        </label>
        <input
          id="document-title"
          className="panel-field__input"
          type="text"
          maxLength={500}
          value={draft.title}
          disabled={disabled}
          onChange={(event) => onChange({ ...draft, title: event.target.value })}
        />
      </div>

      <div className="panel-field">
        <label className="panel-field__label" htmlFor="document-content">
          {t("panel.editor.contentLabel")}
        </label>
        <textarea
          id="document-content"
          className="panel-field__textarea"
          value={draft.content}
          disabled={disabled}
          onChange={(event) => onChange({ ...draft, content: event.target.value })}
        />
      </div>

      <div className="panel-field">
        <label className="panel-field__label" htmlFor="document-comment">
          {t("panel.editor.commentLabel")}
        </label>
        <input
          id="document-comment"
          className="panel-field__input"
          type="text"
          maxLength={500}
          value={draft.changeComment}
          disabled={disabled}
          onChange={(event) => onChange({ ...draft, changeComment: event.target.value })}
        />
        <p className="panel-field__hint">{t("panel.editor.commentHint")}</p>
      </div>
    </>
  );
}
