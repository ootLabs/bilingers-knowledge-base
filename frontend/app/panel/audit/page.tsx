import Link from "next/link";

import { getTranslations } from "@/lib/i18n";

import AuditLog from "./AuditLog";

export default function PanelAuditPage() {
  const t = getTranslations();

  return (
    <>
      <p className="panel-breadcrumb">
        <Link href="/panel/documents">{t("panel.editor.backToList")}</Link>
      </p>
      <h1>{t("panel.audit.heading")}</h1>
      <p className="panel-lead">{t("panel.audit.lead")}</p>
      <AuditLog />
    </>
  );
}
