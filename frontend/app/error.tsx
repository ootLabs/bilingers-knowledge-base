"use client";

import Link from "next/link";

import StatusMessage from "@/components/StatusMessage";
import { getTranslations } from "@/lib/i18n";

/**
 * What a parent sees when a route throws: the 500 of an App Router app.
 *
 * Next passes the thrown `Error` (with a `digest`) into this component, and
 * it is deliberately never destructured. Its message can carry a stack
 * trace, an internal hostname, or a provider name lifted from an upstream
 * response, and once it is bound to a variable it is one careless render
 * away from the screen - which is both the T-63 safety rule and the T-52
 * attack surface. Only `reset` is taken, and only our own copy is shown.
 *
 * Errors thrown by the root layout itself escape this boundary and need
 * `global-error.tsx`. Not added yet: the layout does nothing that can throw
 * today, and an untested second error screen is a liability, not cover.
 */
export default function ErrorScreen({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const t = getTranslations();

  return (
    <main>
      <h1>{t("serverError.heading")}</h1>
      <StatusMessage
        tone="error"
        titleKey="serverError.title"
        descriptionKey="serverError.description"
        action={{ kind: "retry", labelKey: "serverError.retry", onRetry: reset }}
      />
      {/* Second way out: if retrying the same broken route keeps failing,
          the parent still has somewhere to go. */}
      <p className="status-message__fallback">
        <Link href="/">{t("serverError.action")}</Link>
      </p>
    </main>
  );
}
