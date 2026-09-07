import { getTranslations } from "@/lib/i18n";

import ChatPanel from "./ChatPanel";

export default function ChatPage() {
  const t = getTranslations();

  return (
    <main>
      <h1>{t("chat.heading")}</h1>
      <ChatPanel />
    </main>
  );
}
