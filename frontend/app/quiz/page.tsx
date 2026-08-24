import { getTranslations } from "@/lib/i18n";

export default function QuizPage() {
  const t = getTranslations();

  return (
    <main>
      <h1>{t("quiz.heading")}</h1>
      <p>{t("quiz.placeholder")}</p>
    </main>
  );
}
