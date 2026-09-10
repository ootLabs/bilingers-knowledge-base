import { notFound } from "next/navigation";

import { getTranslations } from "@/lib/i18n";

import VersionHistory from "./VersionHistory";

export default async function DocumentHistoryPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const t = getTranslations();
  const { id } = await params;

  // Digits only, tested before parsing. `Number.parseInt` stops at the first
  // character it cannot read, so "7abc", "7.9" and " 7" all came back as 7 and
  // rendered document 7 under an address that means nothing.
  if (!/^\d+$/.test(id)) {
    notFound();
  }
  const documentId = Number.parseInt(id, 10);
  // Zero and anything the database cannot hold as an id are the 404 screen
  // straight away, rather than a request the backend could only refuse.
  if (documentId < 1 || !Number.isSafeInteger(documentId)) {
    notFound();
  }

  return (
    <>
      <h1>{t("panel.history.heading")}</h1>
      <p className="panel-lead">{t("panel.history.lead")}</p>
      <VersionHistory documentId={documentId} />
    </>
  );
}
