import { getTranslations } from "@/lib/i18n";

import LoginForm from "./LoginForm";

// Heading here, logic in the form, matching how /chat is split: the route file
// stays a server component and the client boundary is as small as the feature
// allows.
export default function PanelLoginPage() {
  const t = getTranslations();

  return (
    <>
      <h1>{t("panel.login.heading")}</h1>
      <p className="panel-lead">{t("panel.login.lead")}</p>
      <LoginForm />
    </>
  );
}
