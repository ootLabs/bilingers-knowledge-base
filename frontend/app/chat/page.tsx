import { getTranslations } from "@/lib/i18n";

export default function ChatPage() {
  const t = getTranslations();

  return (
    <main>
      <h1>{t("chat.heading")}</h1>
      <p>{t("chat.placeholder")}</p>
    </main>
  );
}
