import StatusMessage from "@/components/StatusMessage";
import { getTranslations } from "@/lib/i18n";

// Next renders this for any unmatched route. It gets the same shell as every
// other screen (header, tokens, spacing) rather than the framework default,
// so a wrong address looks like part of the product and not like a crash.
export default function NotFound() {
  const t = getTranslations();

  return (
    <main>
      <h1>{t("notFound.heading")}</h1>
      <StatusMessage
        tone="info"
        titleKey="notFound.title"
        descriptionKey="notFound.description"
        action={{ kind: "link", labelKey: "notFound.action", href: "/" }}
      />
    </main>
  );
}
