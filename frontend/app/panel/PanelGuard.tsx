"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import StatusMessage from "@/components/StatusMessage";
import { readPanelToken } from "@/lib/panel-client";

// The whole panel behind one check, rather than each screen remembering to run
// it. A screen that forgets would render the knowledge base to whoever typed
// the address, and it would be a screen, not a policy, that had the bug.
//
// This is not the security boundary and is not meant to be: the backend refuses
// every request without a usable token (see `app.dependencies`). What this
// prevents is a signed-out person seeing an empty panel and a stack of failed
// requests instead of the login form.

const LOGIN_ROUTE = "/panel/login";

type Decision = "checking" | "allowed";

export default function PanelGuard({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [decision, setDecision] = useState<Decision>("checking");

  // The login screen is inside /panel but outside the guard: guarding it would
  // redirect it to itself.
  const isLoginRoute = pathname === LOGIN_ROUTE;

  useEffect(() => {
    if (isLoginRoute || readPanelToken() !== null) {
      setDecision("allowed");
      return;
    }
    setDecision("checking");
    router.replace(LOGIN_ROUTE);
  }, [isLoginRoute, pathname, router]);

  if (decision === "checking") {
    // Never the children: rendering them for one frame is what would fetch
    // with no token and flash a screenful of failures on the way to the login
    // form. The token lives in sessionStorage, which the server cannot read, so
    // this frame exists on every first paint and has to say something calm.
    return (
      <StatusMessage
        tone="info"
        titleKey="panel.checking.title"
        descriptionKey="panel.checking.description"
      />
    );
  }

  return <>{children}</>;
}
