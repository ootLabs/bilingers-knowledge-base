"use client";

import Link from "next/link";

import { getTranslations } from "@/lib/i18n";

// Every state this app can land a user in - empty, failed, out of quota,
// wrong address, crashed - is the same shape: say what happened, then offer
// exactly one way onward. One component for all five keeps that promise
// structural instead of something each screen remembers to honour.

export type StatusTone = "info" | "error" | "limit";

export type StatusAction =
  | { kind: "retry"; labelKey: string; onRetry: () => void }
  | { kind: "link"; labelKey: string; href: string };

export default function StatusMessage({
  tone,
  titleKey,
  descriptionKey,
  action,
}: {
  tone: StatusTone;
  titleKey: string;
  descriptionKey: string;
  action?: StatusAction;
}) {
  const t = getTranslations();

  return (
    <div className={`status-message status-message--${tone}`}>
      {/* h2 rather than h1: every screen using this already has its own h1,
          so a second one would leave the page with two top-level headings. */}
      <h2 className="status-message__title">{t(titleKey)}</h2>
      <p className="status-message__description">{t(descriptionKey)}</p>
      {action?.kind === "retry" && (
        <button type="button" className="cta-button" onClick={action.onRetry}>
          {t(action.labelKey)}
        </button>
      )}
      {action?.kind === "link" && (
        <Link href={action.href} className="cta-button">
          {t(action.labelKey)}
        </Link>
      )}
    </div>
  );
}
