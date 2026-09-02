import { getTranslations } from "@/lib/i18n";

// Acceptance criterion 1 on T-63: this has to be on screen the moment the
// question is sent, not when the first chunk arrives. It is therefore driven
// by the submit handler rather than by the response, and it carries a real
// text label instead of bare animated dots so it means something to a
// screen reader and to anyone with animation switched off.
export default function TypingIndicator() {
  const t = getTranslations();

  return (
    <p className="typing-indicator">
      {t("chat.typing")}
      {/* Decorative: the label above already says it, so the dots are
          hidden from assistive technology rather than read out. */}
      <span className="typing-indicator__dots" aria-hidden="true">
        <span />
        <span />
        <span />
      </span>
    </p>
  );
}
