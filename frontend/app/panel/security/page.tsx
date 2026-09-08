import Link from "next/link";

import { getTranslations } from "@/lib/i18n";

import TwoFactorSetup from "./TwoFactorSetup";

export default function PanelSecurityPage() {
  const t = getTranslations();

  return (
    <>
      <p className="panel-breadcrumb">
        <Link href="/panel/documents">{t("panel.editor.backToList")}</Link>
      </p>
      <h1>{t("panel.twoFactor.heading")}</h1>
      <p className="panel-lead">{t("panel.twoFactor.lead")}</p>
      <TwoFactorSetup />
    </>
  );
}
