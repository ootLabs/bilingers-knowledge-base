import { getTranslations } from "@/lib/i18n";

export default function PlaceholderRoute({
  headingKey,
  placeholderKey,
}: {
  headingKey: string;
  placeholderKey: string;
}) {
  const t = getTranslations();

  return (
    <main>
      <h1>{t(headingKey)}</h1>
      <p>{t(placeholderKey)}</p>
    </main>
  );
}
