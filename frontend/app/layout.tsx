import type { Metadata } from "next";
import { Poppins } from "next/font/google";

import SiteHeader from "@/components/SiteHeader";
import { getTranslations } from "@/lib/i18n";

import "./globals.css";

// Poppins matches the Bilingers-based provisional palette from T-03 (see the
// token comment in globals.css). If the chat's brand turns out to be the
// foundation or Yellow House instead (T-03 open question 1), this is the one
// line that changes together with those tokens.
const poppins = Poppins({
  subsets: ["latin", "latin-ext"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-poppins",
  display: "swap",
});

const t = getTranslations();

export const metadata: Metadata = {
  title: t("common.productName"),
  description: t("common.tagline"),
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="pl" className={poppins.variable}>
      <body>
        <SiteHeader />
        {children}
      </body>
    </html>
  );
}
