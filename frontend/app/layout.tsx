import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Bilingers",
  description: "Inteligentna baza wiedzy o dwujęzyczności",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="pl">
      <body>{children}</body>
    </html>
  );
}
