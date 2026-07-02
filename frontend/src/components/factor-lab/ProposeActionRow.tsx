"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronDown, ChevronRight, Loader2, Play } from "lucide-react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t, type TranslationKey } from "@/lib/i18n";
import {
  proposeFactors,
  pollProposeJob,
  ProposeJobTimeout,
  type ProposeResult,
} from "@/lib/api/factor-lab";
import { parseFactorError } from "@/lib/factor-errors";

// Phase D state machine:
//   idle ──click──► running (jobId set, polling) ──► ok | error
//   ok/error ──click──► running (next run)
//
// 'running' covers both 'queued' (POST returned 202) and 'polling' the
// backend job row. We collapse those to a single visual state per the
// minimal-state model decision: a spinner + elapsed seconds is enough
// signal for the user; per-phase progress would add UI complexity for
// little operational value.
type ProposeState =
  | { kind: "idle" }
  | { kind: "running"; jobId: string; startedAt: number }
  | { kind: "ok"; result: ProposeResult; ts: number }
  | { kind: "error"; message: string; timedOut: boolean };

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
  const [elapsedSec, setElapsedSec] = useState(0);
  // Single source of cancellation for the in-flight poll loop. Survives
  // re-renders via ref so handleClick's closure can abort the previous
  // run if the user double-clicks.
  const abortRef = useRef<AbortController | null>(null);

  // Tick elapsed seconds while running. Cleanup on state change or unmount.
  useEffect(() => {
    if (state.kind !== "running") {
      setElapsedSec(0);
      return;
    }
    const id = setInterval(() => {
      setElapsedSec(Math.floor((Date.now() - state.startedAt) / 1000));
    }, 1000);
    return () => clearInterval(id);
  }, [state]);

  // Cancel polling on unmount.
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  async function handleClick() {
    // Cancel any in-flight poll from a prior click.
    abortRef.current?.abort();
    const ctl = new AbortController();
    abortRef.current = ctl;

    const startedAt = Date.now();
    try {
      const accepted = await proposeFactors(n);

      // Cost-guard short-circuit: backend already wrote a 'done' job and
      // returned the result inline. Skip the poll loop.
      if (accepted.status === "done" && accepted.inline_result) {
        setState({ kind: "ok", result: accepted.inline_result, ts: Date.now() });
        router.refresh();
        return;
      }

      setState({ kind: "running", jobId: accepted.job_id, startedAt });

      const final = await pollProposeJob(accepted.job_id, {
        intervalMs: 3000,
        // 8min budget: the job is now drained by a GitHub Actions runner, which
        // adds ~1-2min of dispatch+startup on top of the 30-180s run. 5min was
        // too tight and surfaced as a false timeout.
        maxAttempts: 160,
        signal: ctl.signal,
      });

      if (ctl.signal.aborted) return;

      if (final.status === "done" && final.result) {
        setState({ kind: "ok", result: final.result, ts: Date.now() });
        router.refresh();
      } else {
        setState({
          kind: "error",
          message: final.error ?? "job finished without result",
          timedOut: false,
        });
      }
    } catch (e) {
      if (ctl.signal.aborted) return;
      if (e instanceof ProposeJobTimeout) {
        setState({
          kind: "error",
          message: t(locale, "factorLab.propose.timedOut"),
          timedOut: true,
        });
        return;
      }
      const msg = e instanceof Error ? e.message : String(e);
      setState({ kind: "error", message: msg, timedOut: false });
    }
  }

  const buttonLabel =
    state.kind === "running"
      ? `${t(locale, "factorLab.propose.running")} · ${elapsedSec}s`
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
                String(
                  state.result.proposed > 0
                    ? state.result.proposed
                    : state.result.evaluated,
                ),
              )}
            </p>
          ) : null}
        </div>
      ) : null}

      {state.kind === "error"
        ? (() => {
            const parsed = parseFactorError(state.message);
            const summary =
              parsed.summary || state.message || `Unknown error`;
            const hasDetail =
              parsed.detail != null && parsed.detail !== summary;
            return (
              <div className="rounded border border-tm-neg/60 bg-tm-neg/10 px-3 py-2 font-tm-mono text-[11px] text-tm-neg">
                <div>
                  {t(locale, "factorLab.propose.errorPrefix")}
                  {": "}
                  {summary}
                </div>
                {hasDetail ? (
                  <details className="mt-1 text-tm-muted">
                    <summary className="cursor-pointer text-[10px]">
                      {t(locale, "backtest.verdict.errorDetails")}
                    </summary>
                    <pre className="mt-1 max-h-32 overflow-auto whitespace-pre-wrap break-all text-[10px]">
                      {parsed.detail}
                    </pre>
                  </details>
                ) : null}
              </div>
            );
          })()
        : null}
    </div>
  );
}
