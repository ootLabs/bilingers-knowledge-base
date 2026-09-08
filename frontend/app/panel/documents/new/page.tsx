import Link from "next/link";

import { getTranslations } from "@/lib/i18n";

import NewDocumentForm from "./NewDocumentForm";

export default function NewDocumentPage() {
  const t = getTranslations();

  return (
    <>
      <p className="panel-breadcrumb">
        <Link href="/panel/documents">{t("panel.editor.backToList")}</Link>
      </p>
      <h1>{t("panel.editor.createHeading")}</h1>
      <p className="panel-lead">{t("panel.editor.createLead")}</p>
      <NewDocumentForm />
    </>
  );
}
