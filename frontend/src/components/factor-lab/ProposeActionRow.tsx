"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Play } from "lucide-react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t, type TranslationKey } from "@/lib/i18n";
import {
  proposeFactors,
  pollProposeJob,
  ProposeJobTimeout,
  type ProposeJobRow,
  type ProposeResult,
} from "@/lib/api/factor-lab";
import { parseFactorError } from "@/lib/factor-errors";
import { TmButton, TmDisclosureButton } from "@/components/tm/TmButton";

type MonitoredJob = { jobId: string; startedAt: number; lastRow: ProposeJobRow | null };

type ProposeState =
  | { kind: "idle" }
  | { kind: "submitting" }
  | ({ kind: "running" | "monitor_paused" } & MonitoredJob)
  | { kind: "ok"; result: ProposeResult; ts: number }
  | { kind: "interrupted"; job: ProposeJobRow }
  | { kind: "error"; message: string; job?: ProposeJobRow };

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

export function ProposeJobProgress({ job, zh }: { readonly job: ProposeJobRow; readonly zh: boolean }) {
  const stages = {
    preparing: zh ? "已领取，准备诊断" : "Claimed · preparing diagnostics",
    generating: zh ? "已开始生成候选" : "Candidate generation started",
    evaluating: zh ? "候选已生成，进入验证" : "Candidates generated · validating",
  };
  const counts = [
    [zh ? "已生成" : "Generated", job.progress?.generated],
    [zh ? "已评估" : "Evaluated", job.result?.evaluated],
    [zh ? "已提交待审" : "Submitted for review", job.result?.proposed],
  ] as const;
  const progress = counts.filter(([, value]) => typeof value === "number")
    .map(([label, value]) => `${label} ${value}`);
  if (job.progress) progress.unshift(stages[job.progress.stage]);
  return progress.length ? <p className="text-tm-muted">{progress.join(" · ")}</p> : null;
}

export function ProposeActionRow({ n = 5 }: ProposeActionRowProps) {
  const { locale } = useLocale();
  const router = useRouter();
  const [state, setState] = useState<ProposeState>({ kind: "idle" });
  const [resultExpanded, setResultExpanded] = useState(false);
  const [elapsedSec, setElapsedSec] = useState(0);
  const zh = locale === "zh";
  const abortRef = useRef<AbortController | null>(null);
  const runningSince = state.kind === "running" ? state.startedAt : null;
  const busy = state.kind === "running" || state.kind === "submitting";

  useEffect(() => {
    if (runningSince === null) {
      setElapsedSec(0);
      return;
    }
    const tick = () => setElapsedSec(Math.floor((Date.now() - runningSince) / 1000));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [runningSince]);

  useEffect(() => () => abortRef.current?.abort(), []);

  async function monitorJob(job: MonitoredJob, signal: AbortSignal) {
    let lastRow = job.lastRow;
    setState({ ...job, kind: "running" });
    try {
      const final = await pollProposeJob(job.jobId, {
        intervalMs: 3000,
        // Allow for dispatch, queue time and the worker's execution budget.
        maxAttempts: 160,
        signal,
        onUpdate(row) {
          lastRow = row;
          if (!signal.aborted) setState({ ...job, kind: "running", lastRow: row });
        },
      });
      if (signal.aborted) return;
      if (final.status === "done" && final.result) {
        setState({ kind: "ok", result: final.result, ts: Date.now() });
        router.refresh();
      } else if (final.error_code === "worker_interrupted") {
        setState({ kind: "interrupted", job: final });
        router.refresh();
      } else {
        setState({ kind: "error", message: final.error ?? "job finished without result", job: final });
        if (final.result?.proposed) router.refresh();
      }
    } catch (error) {
      if (signal.aborted) return;
      if (error instanceof ProposeJobTimeout) lastRow = error.lastRow ?? lastRow;
      setState({ ...job, kind: "monitor_paused", lastRow });
    }
  }

  async function handleClick() {
    if (abortRef.current) return;
    const ctl = new AbortController();
    abortRef.current = ctl;
    try {
      if (state.kind === "monitor_paused") {
        await monitorJob(state, ctl.signal);
        return;
      }
      const startedAt = Date.now();
      setResultExpanded(false);
      setState({ kind: "submitting" });
      const accepted = await proposeFactors(n);
      if (ctl.signal.aborted) return;
      if (accepted.status === "done" && accepted.inline_result) {
        setState({ kind: "ok", result: accepted.inline_result, ts: Date.now() });
        router.refresh();
        return;
      }
      await monitorJob({ jobId: accepted.job_id, startedAt, lastRow: null }, ctl.signal);
    } catch (error) {
      if (!ctl.signal.aborted) {
        setState({ kind: "error", message: error instanceof Error ? error.message : String(error) });
      }
    } finally {
      if (abortRef.current === ctl) abortRef.current = null;
    }
  }

  const buttonLabel = busy
    ? `${t(locale, "factorLab.propose.running")} · ${elapsedSec}s`
    : state.kind === "monitor_paused"
      ? (zh ? "查看原任务" : "Check existing job")
      : state.kind === "interrupted"
        ? (zh ? "发起新提案任务" : "Start a new proposal job")
        : t(locale, "factorLab.propose.button").replace("{n}", String(n));

  return (
    <div className="flex flex-col gap-2">
      <TmButton
        variant="secondary"
        size="sm"
        onClick={handleClick}
        disabled={busy}
        loading={busy}
        loadingLabel={buttonLabel}
        className="w-fit"
      >
        <Play className="h-3.5 w-3.5" strokeWidth={1.75} />
        <span>{buttonLabel}</span>
      </TmButton>

      {state.kind === "running" && state.lastRow ? (
        <ProposeJobProgress job={state.lastRow} zh={zh} />
      ) : null}
      {state.kind === "monitor_paused" ? (
        <div role="status" className="rounded border border-tm-rule bg-tm-bg-2 px-3 py-2 text-xs">
          <p>{zh ? "暂时无法确认任务状态，可继续查看原任务。" : "Job status is temporarily unavailable. You can check the existing job."}</p>
          {state.lastRow ? <ProposeJobProgress job={state.lastRow} zh={zh} /> : null}
        </div>
      ) : null}
      {state.kind === "interrupted" ? (
        <div role="status" className="rounded border border-tm-warn bg-tm-bg-2 px-3 py-2 text-xs">
          <p>{zh ? "提案任务已中断，系统不会自动重跑。" : "Proposal job interrupted. It will not restart automatically."}</p>
          <ProposeJobProgress job={state.job} zh={zh} />
        </div>
      ) : null}

      {state.kind === "ok" ? (
        <div className="flex flex-col gap-1 rounded border border-tm-rule bg-tm-bg-2 px-3 py-2">
          <TmDisclosureButton
            expanded={resultExpanded}
            onClick={() => setResultExpanded((e) => !e)}
            label={
              <span>
              {t(locale, "factorLab.propose.lastResult")}
              {" · "}
              <span className="font-mono">
                {state.result.proposed} / {state.result.evaluated}
              </span>
              {" · "}
              <span className="font-mono">{formatTs(state.ts)}</span>
              </span>
            }
            className="h-auto border-0 bg-transparent px-0 font-tm-mono text-xs text-tm-fg-2 hover:border-transparent hover:bg-transparent hover:text-tm-fg"
          />
          {resultExpanded ? (
            <p className="pl-5 font-tm-mono text-xs text-tm-fg-2">
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
              <div className="rounded border border-tm-neg/60 bg-tm-neg/10 px-3 py-2 font-tm-mono text-xs text-tm-neg">
                <div>
                  {t(locale, "factorLab.propose.errorPrefix")}
                  {": "}
                  {summary}
                </div>
                {state.job ? <ProposeJobProgress job={state.job} zh={zh} /> : null}
                {hasDetail ? (
                  <details className="mt-1 text-tm-muted">
                    <summary className="cursor-pointer text-xs">
                      {t(locale, "backtest.verdict.errorDetails")}
                    </summary>
                    <pre className="mt-1 max-h-32 overflow-auto whitespace-pre-wrap break-all text-xs">
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
