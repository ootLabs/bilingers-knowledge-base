"use client";

import { useCallback, useEffect, useState } from "react";

import StatusMessage from "@/components/StatusMessage";
import { fill, getTranslations } from "@/lib/i18n";
import type { PanelFailure } from "@/lib/panel-client";
import {
  confirmTwoFactor,
  disableTwoFactor,
  getTwoFactorStatus,
  startTwoFactorEnrolment,
  type TwoFactorEnrolment,
  type TwoFactorStatus,
} from "@/lib/panel-two-factor";

import { useSessionRecovery } from "../use-session-recovery";

// Written for the person who has never heard the word TOTP. The instructions
// name what to install, where to type the key, and what the codes are for; the
// words "TOTP", "secret" and "authenticator" appear nowhere on screen except as
// the names of the apps themselves.
//
// The key is shown as text rather than as a QR code, because no QR library is
// installed and adding one is a decision for docs/architecture.md, not a
// drive-by npm install. Typing twelve characters once is a smaller cost than an
// unexamined dependency in the screen that guards the knowledge base.

type Phase = "loading" | "ready" | "enrolling" | "printed";

export default function TwoFactorSetup() {
  const t = getTranslations();
  const recover = useSessionRecovery();
  const [phase, setPhase] = useState<Phase>("loading");
  const [status, setStatus] = useState<TwoFactorStatus | null>(null);
  const [enrolment, setEnrolment] = useState<TwoFactorEnrolment | null>(null);
  const [codes, setCodes] = useState<string[]>([]);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<PanelFailure | null>(null);

  const load = useCallback(async () => {
    setPhase("loading");
    try {
      setStatus(await getTwoFactorStatus());
      setPhase("ready");
    } catch (error) {
      const recovered = recover(error);
      if (recovered !== null) {
        setFailure(recovered);
        setPhase("ready");
      }
    }
  }, [recover]);

  useEffect(() => {
    void load();
  }, [load]);

  async function run(action: () => Promise<void>) {
    if (busy) {
      return;
    }
    setBusy(true);
    setFailure(null);
    try {
      await action();
    } catch (error) {
      setFailure(recover(error));
    } finally {
      setBusy(false);
    }
  }

  if (phase === "loading") {
    return (
      <StatusMessage
        tone="info"
        titleKey="panel.twoFactor.loading.title"
        descriptionKey="panel.twoFactor.loading.description"
      />
    );
  }

  return (
    <>
      <div aria-live="polite">
        {failure !== null && (
          <StatusMessage
            tone="error"
            titleKey={`panel.errors.${failure}.title`}
            descriptionKey={`panel.errors.${failure}.description`}
          />
        )}
      </div>

      {phase === "printed" && (
        <section className="two-factor">
          <h2>{t("panel.twoFactor.codesHeading")}</h2>
          <p>{t("panel.twoFactor.codesLead")}</p>
          <ul className="two-factor__codes">
            {codes.map((printed) => (
              <li key={printed}>{printed}</li>
            ))}
          </ul>
          <p className="panel-field__hint">{t("panel.twoFactor.codesWarning")}</p>
          <button
            type="button"
            className="cta-button"
            onClick={() => {
              setCodes([]);
              void load();
            }}
          >
            {t("panel.twoFactor.codesSaved")}
          </button>
        </section>
      )}

      {phase === "ready" && status?.enabled && (
        <section className="two-factor">
          <p>{t("panel.twoFactor.isOn")}</p>
          <p className="panel-field__hint">
            {fill(t("panel.twoFactor.codesLeft"), { count: status.unusedBackupCodes })}
          </p>
          <div className="panel-field">
            <label className="panel-field__label" htmlFor="two-factor-off-code">
              {t("panel.twoFactor.codeLabel")}
            </label>
            <input
              id="two-factor-off-code"
              className="panel-field__input"
              type="text"
              value={code}
              onChange={(event) => setCode(event.target.value)}
            />
          </div>
          <button
            type="button"
            className="cta-button"
            disabled={busy || code.trim() === ""}
            onClick={() =>
              void run(async () => {
                await disableTwoFactor(code.trim());
                setCode("");
                await load();
              })
            }
          >
            {t("panel.twoFactor.turnOff")}
          </button>
        </section>
      )}

      {phase === "ready" && status?.enabled === false && (
        <section className="two-factor">
          <p>{t("panel.twoFactor.isOff")}</p>
          <ol className="two-factor__steps">
            <li>{t("panel.twoFactor.step1")}</li>
            <li>{t("panel.twoFactor.step2")}</li>
            <li>{t("panel.twoFactor.step3")}</li>
          </ol>
          <button
            type="button"
            className="cta-button"
            disabled={busy}
            onClick={() =>
              void run(async () => {
                setEnrolment(await startTwoFactorEnrolment());
                setPhase("enrolling");
              })
            }
          >
            {t("panel.twoFactor.start")}
          </button>
        </section>
      )}

      {phase === "enrolling" && enrolment !== null && (
        <section className="two-factor">
          <h2>{t("panel.twoFactor.keyHeading")}</h2>
          <p>{t("panel.twoFactor.keyLead")}</p>
          <p className="two-factor__key">{enrolment.secret}</p>
          <div className="panel-field">
            <label className="panel-field__label" htmlFor="two-factor-code">
              {t("panel.twoFactor.confirmLabel")}
            </label>
            <input
              id="two-factor-code"
              className="panel-field__input"
              type="text"
              autoComplete="one-time-code"
              value={code}
              onChange={(event) => setCode(event.target.value)}
            />
          </div>
          <button
            type="button"
            className="cta-button"
            disabled={busy || code.trim() === ""}
            onClick={() =>
              void run(async () => {
                setCodes(await confirmTwoFactor(code.trim()));
                setCode("");
                setPhase("printed");
              })
            }
          >
            {t("panel.twoFactor.confirm")}
          </button>
        </section>
      )}
    </>
  );
}
