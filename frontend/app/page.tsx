import Link from "next/link";

import { getTranslations } from "@/lib/i18n";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
