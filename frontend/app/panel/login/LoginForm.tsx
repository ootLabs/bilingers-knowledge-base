"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import StatusMessage from "@/components/StatusMessage";
import { getTranslations } from "@/lib/i18n";
import { panelLogin, type PanelFailure, toPanelFailure } from "@/lib/panel-client";

// One message for every refusal, on purpose. The backend answers an unknown
// address, a wrong password, a locked account and a deactivated one with the
// same 401 and the same timing (see `app.services.panel_auth`), specifically so
// nobody can find out which addresses have an account. A screen that split them
// apart would hand that back.

const AFTER_LOGIN = "/panel/documents";

type FormState =
  | { phase: "idle" }
  | { phase: "sending" }
  | { phase: "failed"; failure: PanelFailure };

export default function LoginForm() {
  const t = getTranslations();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  // Once the backend has said this account needs a second factor, the field
  // stays on screen: hiding it again after a mistyped code would make the
  // person start the whole login over.
  const [needsCode, setNeedsCode] = useState(false);
  const [state, setState] = useState<FormState>({ phase: "idle" });

  const sending = state.phase === "sending";
  const complete = email.trim() !== "" && password !== "";

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!complete || sending) {
      return;
    }
    setState({ phase: "sending" });
    try {
      await panelLogin({
        email: email.trim(),
        password,
        code: code.trim() || undefined,
      });
      router.replace(AFTER_LOGIN);
    } catch (error) {
      const failure = toPanelFailure(error);
      // `invalid_code` too, not only the prompt: somebody whose browser filled
      // the code in on the first attempt would otherwise be told the code was
      // wrong with no field on screen to correct it.
      if (failure === "second_factor_required" || failure === "invalid_code") {
        setNeedsCode(true);
      }
      setState({ phase: "failed", failure });
    }
  }

  return (
    <form className="panel-form" onSubmit={submit}>
      <div className="panel-field">
        <label className="panel-field__label" htmlFor="panel-email">
          {t("panel.login.emailLabel")}
        </label>
        <input
          id="panel-email"
          className="panel-field__input"
          type="email"
          autoComplete="username"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
      </div>

      <div className="panel-field">
        <label className="panel-field__label" htmlFor="panel-password">
          {t("panel.login.passwordLabel")}
        </label>
        <input
          id="panel-password"
          className="panel-field__input"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
      </div>

      {needsCode && (
        <div className="panel-field">
          <label className="panel-field__label" htmlFor="panel-code">
            {t("panel.login.codeLabel")}
          </label>
          <input
            id="panel-code"
            className="panel-field__input"
            type="text"
            // One-time-code so a phone offers to fill it in; inputMode stays
            // text because a printed backup code has letters in it.
            autoComplete="one-time-code"
            value={code}
            onChange={(event) => setCode(event.target.value)}
          />
          <p className="panel-field__hint">{t("panel.login.codeHint")}</p>
        </div>
      )}

      <button type="submit" className="cta-button" disabled={!complete || sending}>
        {sending ? t("panel.login.submitting") : t("panel.login.submit")}
      </button>

      {/* polite, not assertive: a refused login is not an interruption worth
          cutting off whatever a screen reader is mid-sentence on. */}
      <div className="panel-form__status" aria-live="polite">
        {state.phase === "failed" && (
          <StatusMessage
            tone="error"
            titleKey={`panel.errors.${failureKey(state.failure)}.title`}
            descriptionKey={`panel.errors.${failureKey(state.failure)}.description`}
          />
        )}
      </div>
    </form>
  );
}

/**
 * Which copy answers this failure.
 *
 * `invalid_credentials` keeps its own wording; everything else shares the
 * panel's failure vocabulary. A 503 in particular must not read as "wrong
 * password", or the editor spends the outage retyping a password that was
 * right the first time.
 */
function failureKey(failure: PanelFailure): string {
  return failure === "not_authenticated" ? "invalid_credentials" : failure;
}
