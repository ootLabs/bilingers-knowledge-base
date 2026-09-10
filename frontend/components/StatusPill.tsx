import { getTranslations } from "@/lib/i18n";
import type { DocumentStatus } from "@/lib/panel-documents";

// The single most important thing on the documents screen: whether what you
// are looking at is what a parent is reading, or a draft only the foundation
// can see. It has to be legible without clicking anything, and without
// depending on color, so the shape is a bordered pill with the word in it.
//
// Same rule as the T-63 state surfaces: the border carries the tone, the text
// never does. --color-primary already fails AA on white, and a tinted status
// word would spread that debt to the one label nobody may misread.

export default function StatusPill({ status }: { status: DocumentStatus }) {
  const t = getTranslations();

  return (
    <span className={`status-pill status-pill--${status}`}>
      {t(`panel.status.${status}`)}
    </span>
  );
}
