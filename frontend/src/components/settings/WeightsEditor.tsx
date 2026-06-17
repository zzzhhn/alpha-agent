"use client";

import { useEffect, useState } from "react";
import { TmButton } from "@/components/tm/TmButton";
import { DEFAULT_WEIGHTS, WEIGHTS_KEY } from "@/lib/weights-override";

// Single source of truth: the canonical default + storage key live in
// weights-override.ts so the editor and the client reweight engine never
// drift. Includes supply_chain (serenity seam #2) + the display-only signals.
const KEY = WEIGHTS_KEY;

const DEFAULT_JSON = JSON.stringify(DEFAULT_WEIGHTS, null, 2);

const FORM_LABEL =
  "block text-[10.5px] font-semibold uppercase tracking-[0.06em] text-tm-muted";

export default function WeightsEditor() {
  const [text, setText] = useState(DEFAULT_JSON);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const stored = localStorage.getItem(KEY);
    if (stored) setText(stored);
  }, []);

  function handleSave() {
    try {
      const parsed = JSON.parse(text) as Record<string, unknown>;
      const values = Object.values(parsed);
      if (
        values.length === 0 ||
        !values.every((v) => typeof v === "number" && Number.isFinite(v))
      ) {
        setError("All values must be finite numbers");
        return;
      }
      if ((values as number[]).some((v) => v < 0)) {
        setError("Weights must be >= 0");
        return;
      }
      // The composite renormalizes weights across surviving signals, so the
      // absolute sum is irrelevant — only the relative values matter. We just
      // need at least one positive weight so the normalizer has a denominator.
      const sum = (values as number[]).reduce((a, b) => a + b, 0);
      if (sum <= 0) {
        setError("At least one weight must be > 0");
        return;
      }
      const prev = localStorage.getItem(KEY);
      localStorage.setItem(KEY, text);
      // The native storage event only fires in OTHER tabs; dispatch a synthetic
      // one so card components in THIS tab reweight live (mirrors useFactorMode).
      window.dispatchEvent(
        new StorageEvent("storage", { key: KEY, oldValue: prev, newValue: text }),
      );
      setError(null);
      setSavedAt(new Date().toLocaleTimeString());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Invalid JSON");
    }
  }

  function handleReset() {
    setText(DEFAULT_JSON);
    setError(null);
    setSavedAt(null);
    // Clearing the stored override reverts every card to the backend-canonical
    // composite/rating (readWeightsOverride returns null when the key is gone).
    if (typeof window !== "undefined") {
      const prev = localStorage.getItem(KEY);
      if (prev !== null) {
        localStorage.removeItem(KEY);
        window.dispatchEvent(
          new StorageEvent("storage", { key: KEY, oldValue: prev, newValue: null }),
        );
      }
    }
  }

  return (
    <div className="flex flex-col gap-3 px-3 py-3">
      <label className={FORM_LABEL}>
        JSON: signal → weight (auto-renormalized; relative values matter)
      </label>
      <textarea
        className="h-52 w-full resize-none border border-tm-rule bg-tm-bg-2 p-2 font-tm-mono text-[11px] text-tm-fg outline-none transition-colors focus:border-tm-accent placeholder:text-tm-muted"
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          setError(null);
          setSavedAt(null);
        }}
        spellCheck={false}
      />
      <div className="flex flex-wrap items-center gap-2 border-t border-tm-rule pt-2">
        <TmButton variant="primary" onClick={handleSave}>SAVE</TmButton>
        <TmButton variant="ghost" onClick={handleReset}>RESET TO DEFAULT</TmButton>
        {savedAt ? (
          <span className="font-tm-mono text-[10px] text-tm-pos">SAVED {savedAt}</span>
        ) : null}
        {error ? (
          <span className="font-tm-mono text-[10px] text-tm-neg">{error}</span>
        ) : null}
      </div>
    </div>
  );
}
