import { getTranslations } from "@/lib/i18n";

import DocumentImport from "./DocumentImport";

export default function DocumentImportPage() {
  const t = getTranslations();

  return (
    <>
      <h1>{t("panel.import.heading")}</h1>
      <p className="panel-lead">{t("panel.import.lead")}</p>
      <DocumentImport />
    </>
  );
}
