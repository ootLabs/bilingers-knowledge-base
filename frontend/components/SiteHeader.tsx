import Link from "next/link";

import { getTranslations } from "@/lib/i18n";

const NAV_ITEMS = [
  { href: "/", key: "nav.home" },
  { href: "/chat", key: "nav.chat" },
  { href: "/quiz", key: "nav.quiz" },
  { href: "/account", key: "nav.account" },
] as const;

export default function SiteHeader() {
  const t = getTranslations();

  return (
    <header className="site-header">
      <Link href="/" className="site-header__brand">
        {t("common.productName")}
      </Link>
      <nav aria-label={t("nav.ariaLabel")}>
        <ul className="site-nav">
          {NAV_ITEMS.map((item) => (
            <li key={item.href}>
              <Link href={item.href}>{t(item.key)}</Link>
            </li>
          ))}
        </ul>
      </nav>
    </header>
  );
}
