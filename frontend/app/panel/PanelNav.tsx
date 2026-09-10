"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";

import { getTranslations } from "@/lib/i18n";
import { clearPanelToken, panelLogout, readPanelRole } from "@/lib/panel-client";

// Without this, two of the panel's screens were reachable only by typing their
// address, and a session could be ended only by closing the tab. Both were
// invisible gaps rather than visible ones: nothing on screen was wrong, there
// was simply no way to get anywhere.
//
// The journal is administrators only (the backend answers 403 to an editor), so
// offering it to everybody would be offering an error. The role comes from what
// the login stored, which is a hint for drawing this list and never a
// permission; the backend decides, exactly as with `PanelGuard`.

const LOGIN_ROUTE = "/panel/login";

export default function PanelNav() {
  const t = getTranslations();
  const pathname = usePathname();
  const router = useRouter();
  const [leaving, setLeaving] = useState(false);

  // The login screen renders inside this layout too, and a signed-out person
  // must not be offered a way out of somewhere they have not got into.
  if (pathname === LOGIN_ROUTE) {
    return null;
  }

  async function signOut() {
    if (leaving) {
      return;
    }
    setLeaving(true);
    try {
      // Ends the session on the server too, so a token that has already left
      // this browser cannot be replayed for the rest of its twelve hours.
      await panelLogout();
    } catch {
      // Nothing to tell the person and nothing to retry: they asked to leave,
      // and the half of that which this browser controls happens below.
    } finally {
      // In `finally`, because signing out is the one action that has to happen
      // whatever the network did. `panelLogout` swallows its own failures
      // today, but a version of it that threw would otherwise leave somebody
      // who asked to leave still signed in, looking at a disabled button.
      clearPanelToken();
      router.replace(LOGIN_ROUTE);
    }
  }

  return (
    <nav className="panel-nav" aria-label={t("panel.nav.ariaLabel")}>
      <ul className="panel-nav__links">
        <li>
          <Link href="/panel/documents">{t("panel.nav.documents")}</Link>
        </li>
        <li>
          <Link href="/panel/security">{t("panel.nav.security")}</Link>
        </li>
        {readPanelRole() === "admin" && (
          <li>
            <Link href="/panel/audit">{t("panel.nav.audit")}</Link>
          </li>
        )}
      </ul>
      <button
        type="button"
        className="link-button"
        disabled={leaving}
        onClick={() => void signOut()}
      >
        {leaving ? t("panel.nav.signingOut") : t("panel.nav.signOut")}
      </button>
    </nav>
  );
}
