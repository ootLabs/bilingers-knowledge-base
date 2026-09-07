import Link from "next/link";

import { API_URL } from "@/lib/api-client";
import { getTranslations } from "@/lib/i18n";

export default function Home() {
  const t = getTranslations();

  return (
    <main>
      <h1>{t("landing.heading")}</h1>
      <p>{t("landing.description")}</p>
      <p style={{ color: "var(--color-text-muted)" }}>
        {t("landing.scaffoldNote")} <code>{API_URL}</code>
      </p>
      <Link href="/chat" className="cta-button">
        {t("landing.cta")}
      </Link>
    </main>
  );
}
