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
import { parseFactorError } from "@/lib/factor-errors";
import { addToZoo, removeFromZoo } from "@/lib/factor-zoo";
import type { BacktestParams, Run } from "@/components/backtest/types";

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

// Persisted form memory (mirrors /report's localStorage Pattern C). Re-entering
// /backtest restores the last-used config instead of resetting to defaults.
// Priority is enforced in the mount effect below: explicit sessionStorage
// prefill (a one-shot /alpha or /factors handoff) > this localStorage memory >
// DEFAULT_PARAMS. Both helpers are SSR-safe and never throw (storage can be
// blocked); universe is coerced to SP500 since CSI options were removed.
const BACKTEST_FORM_KEY = "alphacore.backtest.form.v1";

function readBacktestForm(): Partial<BacktestParams> | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(BACKTEST_FORM_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<BacktestParams>;
    if (!parsed || typeof parsed !== "object") return null;
    return { ...parsed, universe: "SP500" };
  } catch {
    return null;
  }
}

function persistBacktestForm(params: BacktestParams): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(BACKTEST_FORM_KEY, JSON.stringify(params));
  } catch {
    /* storage blocked — non-fatal */
  }
}

export default function BacktestPage() {
  const { locale } = useLocale();
  const { toast } = useToast();
  // Seed the form from persisted localStorage on first render (priority below:
  // a sessionStorage prefill handoff still overrides this in the mount effect).
  const session = useBacktestSession(readBacktestForm);

  // Hold name/hypothesis from the prefill so Save-to-Zoo can attach them
  // even after the user has fiddled with the form (specMeta in the hook is
  // already updated; this ref is just a stable handle for the save callback).
  const prefillNameRef = useRef<string | null>(null);
  const prefillHypothesisRef = useRef<string | null>(null);

  // Auto-run guard: prefill triggers exactly one runOnce after params land.
  const autoRanRef = useRef(false);
  const pendingAutoRunRef = useRef(false);

  // Toast dedupe: store the last error message we surfaced via toast so
  // unrelated re-renders (locale toggle, recentRuns mutation, etc.) don't
  // re-fire the same toast.
  const lastErrorToastedRef = useRef<string | null>(null);

  // 1) On mount, resolve the form source by priority: explicit one-shot
  //    sessionStorage prefill (a /alpha or /factors handoff) > localStorage
  //    form memory > DEFAULT_PARAMS. The prefill must win, so localStorage is
  //    only restored when there is no prefill.
  useEffect(() => {
    if (typeof window === "undefined") return;
    let parsed: PrefillPayload | null = null;
    try {
      const raw = window.sessionStorage.getItem(PREFILL_KEY);
      if (raw) {
        window.sessionStorage.removeItem(PREFILL_KEY);
        parsed = JSON.parse(raw) as PrefillPayload;
      }
    } catch {
      parsed = null;
    }

    // No prefill handoff → the localStorage form was already restored in the
    // hook's useState initializer (readBacktestForm), so there is nothing to do.
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

  // 1b) Persist the form on every change so the next visit restores it. On
  //     mount params already equal the restored localStorage value (seeded in
  //     the hook initializer), so the first write is a harmless no-op; a prefill
  //     override re-persists itself, becoming the new last-used config.
  useEffect(() => {
    persistBacktestForm(session.params);
  }, [session.params]);

  // 1c) Reconcile controlled <select> elements to the localStorage-restored
  //     value. React does NOT apply a client-only initial value to a <select>
  //     on the hydration pass (it keeps the SSR-selected option), so direction
  //     / benchmark / mode would visually show defaults even though state is
  //     restored. One forced post-mount re-render (params → identical copy)
  //     runs a normal commit that sets each select's value correctly.
  useEffect(() => {
    session.setParams((p) => ({ ...p }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

  // 3) Surface backtest errors as a toast — but only the parsed summary,
  //    NOT the full 422 envelope (which now lives behind <details> in the
  //    VerdictBar). Dedupe by raw message so renders triggered by unrelated
  //    state changes (locale toggle, etc.) don't re-fire the same toast.
  useEffect(() => {
    if (session.runState.kind !== "error") {
      lastErrorToastedRef.current = null;
      return;
    }
    const raw = session.runState.message;
    if (lastErrorToastedRef.current === raw) return;
    lastErrorToastedRef.current = raw;
    const parsed = parseFactorError(raw);
    toast.error(
      `${t(locale, "backtest.verdict.errorPrefix")}${parsed.summary}`,
    );
  }, [session.runState, toast, locale]);

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
