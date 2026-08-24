import { getTranslations } from "@/lib/i18n";

export default function AccountPage() {
  const t = getTranslations();

  return (
    <main>
      <h1>{t("account.heading")}</h1>
      <p>{t("account.placeholder")}</p>
    </main>
  );
}
