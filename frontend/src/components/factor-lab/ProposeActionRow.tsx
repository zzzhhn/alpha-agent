"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronDown, ChevronRight, Loader2, Play } from "lucide-react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t, type TranslationKey } from "@/lib/i18n";
import { proposeFactors, type ProposeResult } from "@/lib/api/factor-lab";
import { parseFactorError } from "@/lib/factor-errors";

type ProposeState =
  | { kind: "idle" }
  | { kind: "running" }
  | { kind: "ok"; result: ProposeResult; ts: number }
  | { kind: "error"; message: string };

interface ProposeActionRowProps {
  readonly n?: number;
}

function outcomeKey(r: ProposeResult): TranslationKey {
  if (r.dormant) return "factorLab.propose.outcome.dormant";
  if (r.evaluated === 0) return "factorLab.propose.outcome.empty";
  if (r.proposed === 0) return "factorLab.propose.outcome.noBeat";
  return "factorLab.propose.outcome.queued";
}

function formatTs(ts: number): string {
  const d = new Date(ts);
  return d.toTimeString().slice(0, 8);
}

export function ProposeActionRow({ n = 5 }: ProposeActionRowProps) {
  const { locale } = useLocale();
  const router = useRouter();
  const [state, setState] = useState<ProposeState>({ kind: "idle" });
  const [resultExpanded, setResultExpanded] = useState(false);

  async function handleClick() {
    setState({ kind: "running" });
    try {
      const result = await proposeFactors(n);
      setState({ kind: "ok", result, ts: Date.now() });
      router.refresh();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setState({ kind: "error", message: msg });
    }
  }

  const buttonLabel =
    state.kind === "running"
      ? t(locale, "factorLab.propose.running")
      : t(locale, "factorLab.propose.button").replace("{n}", String(n));

  return (
    <div className="flex flex-col gap-2">
      <button
        type="button"
        onClick={handleClick}
        disabled={state.kind === "running"}
        className="inline-flex w-fit items-center gap-2 rounded border border-tm-accent/60 bg-tm-accent px-3 py-1.5 font-tm-mono text-[11px] text-tm-bg transition-opacity disabled:opacity-50 enabled:hover:bg-tm-accent/90"
      >
        {state.kind === "running" ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={1.75} />
        ) : (
          <Play className="h-3.5 w-3.5" strokeWidth={1.75} />
        )}
        <span>{buttonLabel}</span>
      </button>

      {state.kind === "ok" ? (
        <div className="flex flex-col gap-1 rounded border border-tm-rule bg-tm-bg-2 px-3 py-2">
          <button
            type="button"
            onClick={() => setResultExpanded((e) => !e)}
            className="flex items-center gap-2 font-tm-mono text-[11px] text-tm-fg-2"
            aria-expanded={resultExpanded}
          >
            {resultExpanded ? (
              <ChevronDown className="h-3 w-3" strokeWidth={1.75} />
            ) : (
              <ChevronRight className="h-3 w-3" strokeWidth={1.75} />
            )}
            <span>
              {t(locale, "factorLab.propose.lastResult")}
              {" · "}
              <span className="font-mono">
                {state.result.proposed} / {state.result.evaluated}
              </span>
              {" · "}
              <span className="font-mono">{formatTs(state.ts)}</span>
            </span>
          </button>
          {resultExpanded ? (
            <p className="pl-5 font-tm-mono text-[11px] text-tm-fg-2">
              {t(locale, outcomeKey(state.result)).replace(
                "{n}",
                String(state.result.evaluated || state.result.proposed),
              )}
            </p>
          ) : null}
        </div>
      ) : null}

      {state.kind === "error" ? (
        <div className="rounded border border-tm-neg/60 bg-tm-neg/10 px-3 py-2 font-tm-mono text-[11px] text-tm-neg">
          <div>
            {t(locale, "factorLab.propose.errorPrefix")}
            {": "}
            {parseFactorError(state.message).summary}
          </div>
          <details className="mt-1 text-tm-muted">
            <summary className="cursor-pointer text-[10px]">
              {t(locale, "backtest.verdict.errorDetails")}
            </summary>
            <pre className="mt-1 max-h-32 overflow-auto whitespace-pre-wrap break-all text-[10px]">
              {state.message}
            </pre>
          </details>
        </div>
      ) : null}
    </div>
  );
}
