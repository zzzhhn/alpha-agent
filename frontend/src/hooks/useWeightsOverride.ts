// frontend/src/hooks/useWeightsOverride.ts
// Shared client-side hook for the PERSONAL weight override.
//
// localStorage key (alpha-agent:weights) is the single source of truth:
// WeightsEditor (settings) writes it; card components read it + listen to
// storage events so a Save in settings immediately reweights the cards in
// every tab (and, via the editor's synthetic event, the same tab too).
//
// SSR-safe: returns null on the server + first client render (so server HTML
// and first client render agree — no hydration mismatch); the post-mount
// effect hydrates the real override + subscribes to changes. null means
// "no override — render the backend-canonical card unchanged".
"use client";

import { useEffect, useState } from "react";

import { readWeightsOverride, WEIGHTS_KEY } from "@/lib/weights-override";

export function useWeightsOverride(): Record<string, number> | null {
  const [weights, setWeights] = useState<Record<string, number> | null>(null);

  useEffect(() => {
    setWeights(readWeightsOverride());
    const onStorage = (e: StorageEvent) => {
      if (e.key !== WEIGHTS_KEY) return;
      if (e.oldValue === e.newValue) return;
      setWeights(readWeightsOverride());
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  return weights;
}
