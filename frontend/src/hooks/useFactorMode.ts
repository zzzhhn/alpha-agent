// frontend/src/hooks/useFactorMode.ts
// Shared client-side hook for the SHORT/LONG factor toggle.
//
// localStorage key is the single source of truth across pages: PicksBrowser
// writes it (the canonical toggle UI), Stock detail components read it +
// listen to storage events so a flip on /picks immediately propagates to
// the stock detail in another tab.
//
// SSR-safe: the initial render uses the "short" default so server HTML and
// first client render agree (no hydration mismatch); the post-mount effect
// hydrates the real preference + subscribes to changes.
"use client";

import { useEffect, useState, useCallback } from "react";

import type { FactorMode } from "@/lib/api/picks";

export const FACTOR_MODE_KEY = "alpha:factor_mode";

function readModePref(): FactorMode {
  if (typeof window === "undefined") return "short";
  const v = window.localStorage.getItem(FACTOR_MODE_KEY);
  return v === "long" ? "long" : "short";
}

export function useFactorMode(): [FactorMode, (next: FactorMode) => void] {
  const [mode, setMode] = useState<FactorMode>("short");

  // Hydrate after mount + subscribe to cross-tab storage events. Skip the
  // listener when oldValue === newValue so the setter's own synthetic event
  // (intended to notify SIBLING components in the same tab) does not also
  // fire a redundant setMode on the setter's own component.
  useEffect(() => {
    setMode(readModePref());
    const onStorage = (e: StorageEvent) => {
      if (e.key !== FACTOR_MODE_KEY) return;
      if (e.oldValue === e.newValue) return;
      setMode(e.newValue === "long" ? "long" : "short");
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  // setter — also writes to localStorage so other tabs / sibling components
  // receive the change via the storage event above (but not in the same
  // tab; that's why we update local state directly as well).
  const setModeAndPersist = useCallback((next: FactorMode) => {
    setMode(next);
    if (typeof window !== "undefined") {
      const prev = window.localStorage.getItem(FACTOR_MODE_KEY);
      window.localStorage.setItem(FACTOR_MODE_KEY, next);
      // Manually dispatch a same-tab storage event so other components in
      // this tab listening via this hook also update. The native storage
      // event only fires for OTHER tabs. Include oldValue so the listener
      // can detect no-op flips and skip its redundant setMode.
      window.dispatchEvent(
        new StorageEvent("storage", {
          key: FACTOR_MODE_KEY,
          oldValue: prev,
          newValue: next,
        }),
      );
    }
  }, []);

  return [mode, setModeAndPersist];
}
