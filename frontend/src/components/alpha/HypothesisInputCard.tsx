"use client";

import { ChevronDown, History, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { FactorUniverse } from "@/lib/types";

// ---- Prop types ----

export interface InputCardExample {
  readonly label: string;
  readonly text: string;
}

/**
 * Mirrors the real `HypothesisHistoryEntry` from lib/types.ts.
 * Extra fields are typed as optional so the parent can pass the
 * full richer object without a type error.
 */
export interface InputCardHistoryEntry {
  readonly id: string;
  readonly timestamp: string;
  readonly isFavorite?: boolean;
  readonly request: {
    readonly text: string;
    readonly universe?: FactorUniverse;
  };
  readonly result?: {
    readonly spec?: {
      readonly expression?: string;
    };
  };
}

interface Props {
  readonly text: string;
  readonly onTextChange: (s: string) => void;
  readonly universe: FactorUniverse;
  readonly onUniverseChange: (u: FactorUniverse) => void;
  readonly onSubmit: () => void;
  readonly disabled: boolean;
  readonly examples: ReadonlyArray<InputCardExample>;
  readonly history: ReadonlyArray<InputCardHistoryEntry>;
  readonly onHistorySelect: (entry: InputCardHistoryEntry) => void;
}

// FactorUniverse = "CSI300" | "CSI500" | "SP500" | "custom"
const UNIVERSES: FactorUniverse[] = ["SP500", "CSI300", "CSI500", "custom"];

// ---- Component ----

export function HypothesisInputCard(p: Props) {
  const [historyOpen, setHistoryOpen] = useState(false);
  const popoverRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!historyOpen) return;
    function handler(e: MouseEvent) {
      if (
        popoverRef.current &&
        !popoverRef.current.contains(e.target as Node)
      ) {
        setHistoryOpen(false);
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [historyOpen]);

  const empty = p.text.trim().length === 0;

  return (
    <section className="flex flex-col gap-3 rounded border border-tm-rule bg-tm-bg-2 p-4">
      {/* Header row: section title + History popover trigger */}
      <header className="flex items-center justify-between">
        <h2 className="font-tm-mono text-[11px] font-semibold tracking-widest text-tm-fg">
          HYPOTHESIS INPUT
        </h2>

        {/* History popover */}
        <div className="relative" ref={popoverRef}>
          <button
            type="button"
            onClick={() => setHistoryOpen((o) => !o)}
            className="inline-flex items-center gap-1 rounded border border-tm-rule px-2 py-1 font-tm-mono text-[11px] text-tm-fg-2 transition-colors hover:border-tm-accent hover:text-tm-fg"
          >
            <History className="h-3.5 w-3.5" strokeWidth={1.75} />
            <span>HISTORY</span>
            <ChevronDown
              className={`h-3 w-3 transition-transform ${historyOpen ? "rotate-180" : ""}`}
              strokeWidth={1.75}
            />
          </button>

          {historyOpen && (
            <div className="absolute right-0 top-full z-10 mt-1 max-h-[400px] w-[380px] overflow-y-auto rounded border border-tm-rule bg-tm-bg-2 shadow-lg">
              {p.history.length === 0 ? (
                <div className="px-3 py-4 font-tm-mono text-[11px] text-tm-muted">
                  No saved hypotheses yet.
                </div>
              ) : (
                <ul>
                  {p.history.map((h) => (
                    <li key={h.id} className="border-b border-tm-rule last:border-b-0">
                      <button
                        type="button"
                        onClick={() => {
                          p.onHistorySelect(h);
                          setHistoryOpen(false);
                        }}
                        className="block w-full px-3 py-2 text-left transition-colors hover:bg-tm-bg-3"
                      >
                        <div className="line-clamp-2 font-tm-mono text-[11px] text-tm-fg-2 hover:text-tm-fg">
                          {h.request.text}
                        </div>
                        {h.result?.spec?.expression && (
                          <code className="mt-0.5 block truncate font-tm-mono text-[10px] text-tm-muted">
                            {h.result.spec.expression}
                          </code>
                        )}
                        <div className="mt-1 font-tm-mono text-[10px] text-tm-muted">
                          {h.timestamp}
                          {h.isFavorite && (
                            <span className="ml-2 text-tm-warn">★</span>
                          )}
                        </div>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      </header>

      {/* Main textarea */}
      <textarea
        value={p.text}
        onChange={(e) => p.onTextChange(e.target.value)}
        placeholder="e.g. 12-month momentum minus 6-month volatility, neutralized by sector"
        className="min-h-[96px] resize-y rounded border border-tm-rule bg-tm-bg-3 p-3 font-tm-mono text-sm text-tm-fg placeholder:text-tm-muted focus:border-tm-accent focus:outline-none disabled:opacity-50"
        disabled={p.disabled}
      />

      {/* Example chips — only when textarea is empty */}
      {empty && p.examples.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-tm-mono text-[10px] text-tm-muted">
            EXAMPLES:
          </span>
          {p.examples.map((ex) => (
            <button
              key={ex.label}
              type="button"
              onClick={() => p.onTextChange(ex.text)}
              className="inline-flex items-center gap-1 rounded-full border border-tm-rule px-2.5 py-0.5 font-tm-mono text-[11px] text-tm-fg-2 transition-colors hover:border-tm-accent hover:text-tm-accent"
            >
              <Sparkles className="h-3 w-3" strokeWidth={1.75} />
              {ex.label}
            </button>
          ))}
        </div>
      )}

      {/* Footer row: char count + universe selector + primary action */}
      <div className="flex items-center justify-between gap-3">
        <div className="font-tm-mono text-[10px] tabular-nums text-tm-muted">
          {p.text.length} chars
        </div>

        <div className="flex items-center gap-2">
          {/* Universe selector */}
          <select
            value={p.universe}
            onChange={(e) =>
              p.onUniverseChange(e.target.value as FactorUniverse)
            }
            className="rounded border border-tm-rule bg-tm-bg-3 px-2 py-1 font-tm-mono text-[11px] text-tm-fg focus:border-tm-accent focus:outline-none"
          >
            {UNIVERSES.map((u) => (
              <option key={u} value={u}>
                {u}
              </option>
            ))}
          </select>

          {/* Primary action */}
          <button
            type="button"
            onClick={p.onSubmit}
            disabled={p.disabled || empty}
            className="rounded bg-tm-accent px-4 py-2 font-tm-mono text-sm font-semibold text-tm-bg transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            TRANSLATE &amp; BACKTEST
          </button>
        </div>
      </div>
    </section>
  );
}
