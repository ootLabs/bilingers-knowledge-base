"use client";

import { useRouter } from "next/navigation";
import { useCallback, useRef } from "react";

import { clearPanelToken, type PanelFailure, toPanelFailure } from "@/lib/panel-client";

/**
 * Turn anything a panel call threw into a failure key, and handle the one key
 * that is not a message but an exit.
 *
 * A 401 mid-session means the token stopped working: expired, revoked, or the
 * account switched off. There is nothing for the editor to read and nothing to
 * retry, so the screen it happened on hands over to the login form instead of
 * explaining itself. Every other failure comes back as a key for the caller to
 * render.
 *
 * One hook rather than the same four lines on four screens: the screen that
 * forgot them would leave someone signed out staring at an error they cannot
 * act on.
 *
 * The returned function never changes identity, and that is load bearing, not
 * tidiness. Every panel screen puts it in the dependency list of the
 * `useCallback` that loads its data, and that callback in the dependency list
 * of a `useEffect`. If this function were rebuilt on each render, the effect
 * would refire on each render, set state, and render again: an infinite loop
 * rather than a screen. The router is held in a ref so the callback can reach
 * the current one without depending on it.
 */
export function useSessionRecovery(): (error: unknown) => PanelFailure | null {
  const router = useRouter();
  const routerRef = useRef(router);
  routerRef.current = router;

  return useCallback((error: unknown) => {
    const failure = toPanelFailure(error);
    if (failure === "not_authenticated") {
      clearPanelToken();
      routerRef.current.replace("/panel/login");
      return null;
    }
    return failure;
  }, []);
}
