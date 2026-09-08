"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import StatusMessage from "@/components/StatusMessage";
import StatusPill from "@/components/StatusPill";
import { formatDateTime } from "@/lib/format-date";
import { getTranslations } from "@/lib/i18n";
import type { PanelFailure } from "@/lib/panel-client";
import { listDocuments, type DocumentStatus, type DocumentSummary } from "@/lib/panel-documents";

import { useSessionRecovery } from "../use-session-recovery";

// The screen the editor lands on. If she cannot find the document she is
// looking for here in about five seconds, the panel is dead and the foundation
// goes back to mailing files around, so every row answers the three questions
// that make it findable at a glance: what it is called, what state it is in,
// and when it last moved.
//
// Filtering happens in the browser, not in a query string. The foundation's
// base is tens of documents, the whole list is already in hand, and a
// round trip per keystroke would make search feel slower than scrolling.

const STATUSES: DocumentStatus[] = ["draft", "in_review", "published", "withdrawn"];

type ListState =
  | { phase: "loading" }
  | { phase: "failed"; failure: PanelFailure }
  | { phase: "ready"; documents: DocumentSummary[] };

type StatusFilter = DocumentStatus | "all";

export default function DocumentsList() {
  const t = getTranslations();
  const recover = useSessionRecovery();
  const [state, setState] = useState<ListState>({ phase: "loading" });
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [newestFirst, setNewestFirst] = useState(true);

  const load = useCallback(async () => {
    setState({ phase: "loading" });
    try {
      setState({ phase: "ready", documents: await listDocuments() });
    } catch (error) {
      const failure = recover(error);
      // null means the session is gone and `recover` has already sent the
      // editor to the login screen; there is nothing left to render here.
      if (failure !== null) {
        setState({ phase: "failed", failure });
      }
    }
  }, [recover]);

  useEffect(() => {
    void load();
  }, [load]);

  const visible = useMemo(() => {
    if (state.phase !== "ready") {
      return [];
    }
    const needle = query.trim().toLocaleLowerCase("pl");
    return state.documents
      .filter((document) => status === "all" || document.latestVersion.status === status)
      .filter(
        (document) =>
          needle === "" ||
          document.latestVersion.title.toLocaleLowerCase("pl").includes(needle),
      )
      .sort((left, right) => {
        const order = left.latestVersion.createdAt.localeCompare(right.latestVersion.createdAt);
        return newestFirst ? -order : order;
      });
  }, [newestFirst, query, state, status]);

  if (state.phase === "loading") {
    return (
      <StatusMessage
        tone="info"
        titleKey="panel.documents.loading.title"
        descriptionKey="panel.documents.loading.description"
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

  // Nothing in the base at all is a different situation from nothing matching
  // the filters, and it gets a different way onward: one creates a document,
  // the other clears what is hiding them.
  if (state.documents.length === 0) {
    return (
      <StatusMessage
        tone="info"
        titleKey="panel.documents.empty.title"
        descriptionKey="panel.documents.empty.description"
        action={{
          kind: "link",
          labelKey: "panel.documents.create",
          href: "/panel/documents/new",
        }}
      />
    );
  }

  return (
    <div className="document-index">
      <div className="document-index__actions">
        <Link href="/panel/documents/new" className="cta-button">
          {t("panel.documents.create")}
        </Link>
        <Link href="/panel/documents/import">{t("panel.documents.import")}</Link>
      </div>

      <div className="document-filters">
        <div className="panel-field">
          <label className="panel-field__label" htmlFor="document-search">
            {t("panel.documents.searchLabel")}
          </label>
          <input
            id="document-search"
            className="panel-field__input"
            type="search"
            value={query}
            placeholder={t("panel.documents.searchPlaceholder")}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>

        <div className="panel-field">
          <label className="panel-field__label" htmlFor="document-status">
            {t("panel.documents.statusLabel")}
          </label>
          <select
            id="document-status"
            className="panel-field__input"
            value={status}
            onChange={(event) => setStatus(event.target.value as StatusFilter)}
          >
            <option value="all">{t("panel.documents.statusAll")}</option>
            {STATUSES.map((value) => (
              <option key={value} value={value}>
                {t(`panel.status.${value}`)}
              </option>
            ))}
          </select>
        </div>

        <div className="panel-field">
          <label className="panel-field__label" htmlFor="document-order">
            {t("panel.documents.orderLabel")}
          </label>
          <select
            id="document-order"
            className="panel-field__input"
            value={newestFirst ? "newest" : "oldest"}
            onChange={(event) => setNewestFirst(event.target.value === "newest")}
          >
            <option value="newest">{t("panel.documents.orderNewest")}</option>
            <option value="oldest">{t("panel.documents.orderOldest")}</option>
          </select>
        </div>
      </div>

      {visible.length === 0 ? (
        <StatusMessage
          tone="info"
          titleKey="panel.documents.noMatches.title"
          descriptionKey="panel.documents.noMatches.description"
          action={{
            kind: "retry",
            labelKey: "panel.documents.clearFilters",
            onRetry: () => {
              setQuery("");
              setStatus("all");
            },
          }}
        />
      ) : (
        <ul className="document-list">
          {visible.map((document) => (
            <li key={document.id} className="document-row">
              <div className="document-row__heading">
                <Link href={`/panel/documents/${document.id}`} className="document-row__title">
                  {document.latestVersion.title}
                </Link>
                <StatusPill status={document.latestVersion.status} />
              </div>
              <p className="document-row__meta">
                {t("panel.documents.changedOn")} {formatDateTime(document.latestVersion.createdAt)}
                {document.latestVersion.authorEmail !== null && (
                  <>
                    {", "}
                    {t("panel.documents.changedBy")} {document.latestVersion.authorEmail}
                  </>
                )}
              </p>
              <p className="document-row__links">
                <Link href={`/panel/documents/${document.id}`}>
                  {t("panel.documents.edit")}
                </Link>
                <Link href={`/panel/documents/${document.id}/history`}>
                  {t("panel.documents.history")}
                </Link>
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
