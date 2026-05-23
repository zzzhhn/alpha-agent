"use client";

/**
 * Backtest page — thin orchestrator (v3 redesign T8).
 *
 * Wires `useBacktestSession` to the 5 redesign components:
 *   FORM (sticky) → VERDICT BAR → EVIDENCE GRID → ANALYTICS GROUPS → RECENT RUNS
 *
 * Preserved from the pre-redesign page:
 *   1. PREFILL_KEY handoff from /alpha or /factors via sessionStorage —
 *      consumed once on mount, mapped into `params` + `specMeta`, then
 *      `runOnce` is auto-fired if a prefill expression was supplied.
 *   2. Save-to-Zoo with the same `headlineMetrics` shape the legacy
 *      ZooSaveButton emitted (testSharpe / totalReturn / testIc), plus
 *      the full backtest config so /factors replay is reproducible.
 *   3. Undo toast that removes the entry from the Zoo on click.
 *
 * All 9 inline analytics panes that previously lived in this file are now
 * mounted via <BacktestAnalyticsGroups />. The legacy inline pane functions
 * and their helpers are gone.
 */

import { useCallback, useEffect, useRef } from "react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { useToast } from "@/components/ui/toast";
import { useBacktestSession } from "@/components/backtest/useBacktestSession";
import { BacktestFormSticky } from "@/components/backtest/BacktestFormSticky";
import { BacktestVerdictBar } from "@/components/backtest/BacktestVerdictBar";
import { BacktestEvidenceGrid } from "@/components/backtest/BacktestEvidenceGrid";
import { BacktestAnalyticsGroups } from "@/components/backtest/BacktestAnalyticsGroups";
import { RecentRunsTable } from "@/components/backtest/RecentRunsTable";
import { addToZoo, removeFromZoo } from "@/lib/factor-zoo";
import type { Run } from "@/components/backtest/types";

/**
 * Shape of the sessionStorage handoff blob written by /alpha and /factors.
 * Kept structurally identical to the legacy page's PrefillPayload so
 * upstream writers don't need to change.
 */
interface PrefillPayload {
  readonly name: string;
  readonly expression: string;
  readonly operators_used: readonly string[];
  readonly lookback: number;
  readonly hypothesis?: string;
  readonly direction?: "long_short" | "long_only" | "short_only";
  readonly neutralize?: "none" | "sector";
  readonly benchmarkTicker?: "SPY" | "RSP";
  readonly mode?: "static" | "walk_forward";
  readonly topPct?: number;       // 0–1 fraction (legacy)
  readonly bottomPct?: number;    // 0–1 fraction (legacy)
  readonly transactionCostBps?: number;
}

const PREFILL_KEY = "alphacore.backtest.prefill.v1";

export default function BacktestPage() {
  const { locale } = useLocale();
  const { toast } = useToast();
  const session = useBacktestSession();

  // Hold name/hypothesis from the prefill so Save-to-Zoo can attach them
  // even after the user has fiddled with the form (specMeta in the hook is
  // already updated; this ref is just a stable handle for the save callback).
  const prefillNameRef = useRef<string | null>(null);
  const prefillHypothesisRef = useRef<string | null>(null);

  // Auto-run guard: prefill triggers exactly one runOnce after params land.
  const autoRanRef = useRef(false);
  const pendingAutoRunRef = useRef(false);

  // 1) Consume sessionStorage prefill once on mount → drive params + specMeta.
  useEffect(() => {
    if (typeof window === "undefined") return;
    let parsed: PrefillPayload | null = null;
    try {
      const raw = window.sessionStorage.getItem(PREFILL_KEY);
      if (!raw) return;
      window.sessionStorage.removeItem(PREFILL_KEY);
      parsed = JSON.parse(raw) as PrefillPayload;
    } catch {
      return;
    }
    if (!parsed?.expression) return;

    prefillNameRef.current = parsed.name ?? null;
    prefillHypothesisRef.current = parsed.hypothesis ?? null;

    // Map prefill → BacktestParams. UI carries top/bottomPct as 0–100 percentages;
    // legacy PrefillPayload sent fractions (0.01–0.50), so multiply by 100.
    session.setParams((prev) => ({
      ...prev,
      expression: parsed!.expression,
      operatorsUsed: parsed!.operators_used,
      lookback: parsed!.lookback,
      direction: parsed!.direction ?? prev.direction,
      neutralize:
        parsed!.neutralize !== undefined
          ? parsed!.neutralize === "sector"
          : prev.neutralize,
      benchmark: parsed!.benchmarkTicker ?? prev.benchmark,
      mode: parsed!.mode ?? prev.mode,
      topPct: parsed!.topPct !== undefined ? parsed!.topPct * 100 : prev.topPct,
      bottomPct:
        parsed!.bottomPct !== undefined
          ? parsed!.bottomPct * 100
          : prev.bottomPct,
      transactionCostBps:
        parsed!.transactionCostBps ?? prev.transactionCostBps,
    }));
    session.setSpecMeta((prev) => ({
      name: parsed!.name ?? prev.name,
      hypothesis: parsed!.hypothesis ?? prev.hypothesis,
      justification: prev.justification,
    }));

    pendingAutoRunRef.current = true;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // mount-only — session setters are stable

  // 2) Once the params reflect the prefill, fire runOnce exactly once.
  useEffect(() => {
    if (
      pendingAutoRunRef.current &&
      !autoRanRef.current &&
      session.params.expression !== "" &&
      session.runState.kind === "idle"
    ) {
      autoRanRef.current = true;
      pendingAutoRunRef.current = false;
      void session.runOnce();
    }
  }, [session.params.expression, session.runState.kind, session.runOnce, session]);

  // Save-to-Zoo: works for the current run (no arg) or any past run (by id).
  const handleSaveToZoo = useCallback(
    (runId?: string) => {
      const run: Run | null = runId
        ? session.recentRuns.find((r) => r.id === runId) ?? null
        : session.currentRun;
      if (!run) return;

      const totalReturn = run.raw.test_metrics?.total_return;
      try {
        const saved = addToZoo({
          name:
            prefillNameRef.current ??
            session.specMeta.name ??
            run.params.expression.slice(0, 60),
          expression: run.params.expression,
          hypothesis:
            prefillHypothesisRef.current ?? session.specMeta.hypothesis ?? "",
          intuition: session.specMeta.justification,
          direction: run.params.direction,
          neutralize: run.params.neutralize ? "sector" : "none",
          benchmarkTicker: run.params.benchmark,
          mode: run.params.mode,
          topPct: run.params.topPct / 100,
          bottomPct: run.params.bottomPct / 100,
          transactionCostBps: run.params.transactionCostBps,
          headlineMetrics: {
            testSharpe: run.metrics.sharpe ?? undefined,
            totalReturn: totalReturn ?? undefined,
            testIc: run.metrics.ic ?? undefined,
          },
        });
        toast.success(
          t(locale, "backtest.runs.savedToast" as Parameters<typeof t>[1]),
          {
            action: {
              label: t(
                locale,
                "backtest.runs.undo" as Parameters<typeof t>[1],
              ),
              onClick: () => removeFromZoo(saved.id),
            },
          },
        );
      } catch (e) {
        toast.error(
          (e instanceof Error ? e.message : String(e)) || "Save failed",
        );
      }
    },
    [session, toast, locale],
  );

  const handleTogglePinCurrent = useCallback(() => {
    if (session.currentRun) session.togglePin(session.currentRun.id);
  }, [session]);

  return (
    <main className="flex flex-col">
      <BacktestFormSticky
        params={session.params}
        setParams={session.setParams}
        isRunning={session.isRunning}
        onRun={session.runOnce}
      />
      <div className="flex flex-col gap-4 p-4">
        <BacktestVerdictBar
          runState={session.runState}
          currentRun={session.currentRun}
          deltas={session.deltas}
          thresholds={session.thresholds}
          baselineRunId={session.baselineRunId}
          recentRunsCount={session.recentRuns.length}
          onSaveToZoo={() => handleSaveToZoo()}
          onTogglePin={handleTogglePinCurrent}
          onReRun={session.runOnce}
        />
        <BacktestEvidenceGrid
          runState={session.runState}
          currentRun={session.currentRun}
        />
        <BacktestAnalyticsGroups currentRun={session.currentRun} />
        <RecentRunsTable
          runs={session.recentRuns}
          baselineRunId={session.baselineRunId}
          onRefill={session.refillFromRun}
          onTogglePin={session.togglePin}
          onSaveToZoo={handleSaveToZoo}
        />
      </div>
    </main>
  );
}
