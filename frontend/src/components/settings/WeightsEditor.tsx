"use client";

import { useEffect, useState } from "react";
import { TmButton } from "@/components/tm/TmButton";

const KEY = "alpha-agent:weights";

const DEFAULT_WEIGHTS: Record<string, number> = {
  factor: 0.30,
  technicals: 0.20,
  analyst: 0.10,
  earnings: 0.10,
  news: 0.10,
  insider: 0.05,
  options: 0.05,
  premarket: 0.05,
  macro: 0.05,
  calendar: 0.00,
};

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
      if (!values.every((v) => typeof v === "number")) {
        setError("All values must be numbers");
        return;
      }
      const sum = (values as number[]).reduce((a, b) => a + b, 0);
      if (Math.abs(sum - 1.0) > 0.05) {
        setError(`Weights must sum to ~1.0 (got ${sum.toFixed(3)})`);
        return;
      }
      localStorage.setItem(KEY, text);
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
  }

  return (
    <div className="flex flex-col gap-3 px-3 py-3">
      <label className={FORM_LABEL}>
        JSON — signal → weight (sum ≈ 1.0)
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
