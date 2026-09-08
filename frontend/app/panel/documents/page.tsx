import { getTranslations } from "@/lib/i18n";

import DocumentsList from "./DocumentsList";

export default function PanelDocumentsPage() {
  const t = getTranslations();

  return (
    <>
      <h1>{t("panel.documents.heading")}</h1>
      <p className="panel-lead">{t("panel.documents.lead")}</p>
      <DocumentsList />
    </>
  );
}
