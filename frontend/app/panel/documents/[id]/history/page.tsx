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
  const documentId = Number.parseInt(id, 10);

  if (!Number.isInteger(documentId) || documentId < 1) {
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
