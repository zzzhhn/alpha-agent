"use client";

/**
 * RecentRunsTable — session-only N=10 table of past runs (T7).
 *
 * Displays the recentRuns array (newest first; cap 10) supplied by the page
 * via useBacktestSession. Per-row actions (refill / pin / save-to-zoo) emit
 * callbacks; the page-level orchestrator (T8) wires those to its toast +
 * undo flow. This component is purely render + emit — no useToast here.
 *
 * Threshold glyph logic mirrors BacktestVerdictBar (T4) verbatim per spec
 * §8.2. Duplicated inline for now; T8 review can decide if extraction is
 * worth it.
 */

import { Bookmark, RotateCcw, Star } from "lucide-react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { TmPane } from "@/components/tm/TmPane";
import type { BacktestParams, Run } from "./types";

interface RecentRunsTableProps {
  readonly runs: readonly Run[];
  readonly baselineRunId: string | null;
  readonly onRefill: (runId: string) => void;
  readonly onTogglePin: (runId: string) => void;
  readonly onSaveToZoo: (runId: string) => void;
}

/* ---------- Threshold classifiers (per spec §8.2; mirror VerdictBar) ---------- */

type TrafficLight = "ok" | "warn" | "bad";

const TH_SHARPE_OK = 1.0;
const TH_SHARPE_WARN = 0.5;
const TH_MAXDD_OK = -0.15;
const TH_MAXDD_BAD = -0.25;
const TH_IC_OK = 0.02;

function classifySharpe(v: number): TrafficLight {
  if (v >= TH_SHARPE_OK) return "ok";
  if (v >= TH_SHARPE_WARN) return "warn";
  return "bad";
}

function classifyMaxDD(v: number): TrafficLight {
  // maxDD is negative; closer to 0 is better.
  if (v >= TH_MAXDD_OK) return "ok";
  if (v >= TH_MAXDD_BAD) return "warn";
  return "bad";
}

function classifyIC(v: number): TrafficLight {
  if (v >= TH_IC_OK) return "ok";
  if (v >= 0) return "warn";
  return "bad";
}

const GLYPH_CLASS: Record<TrafficLight, string> = {
  ok: "text-tm-pos",
  warn: "text-tm-warn",
  bad: "text-tm-neg",
};

const GLYPH_CHAR: Record<TrafficLight, string> = {
  ok: "✓", // ✓
  warn: "⚠", // ⚠
  bad: "✗", // ✗
};

/* ---------- Value formatters ---------- */

function fmtSharpe(v: number | null): string {
  return v === null ? "—" : v.toFixed(2);
}

function fmtMaxDD(v: number | null): string {
  return v === null ? "—" : `${(v * 100).toFixed(1)}%`;
}

function fmtIC(v: number | null): string {
  return v === null ? "—" : v.toFixed(4);
}

function fmtTurnover(v: number | null): string {
  return v === null ? "—" : `${(v * 100).toFixed(0)}%`;
}

function fmtAnnReturn(v: number | null): string {
  return v === null ? "—" : `${(v * 100).toFixed(1)}%`;
}

/* ---------- Params summary ---------- */

function formatParamsSummary(p: BacktestParams): string {
  const dir =
    p.direction === "long_short"
      ? "LS"
      : p.direction === "long_only"
      ? "LO"
      : "SO";
  const parts = [`top=${p.topPct}%`, `dir=${dir}`, `univ=${p.universe}`];
  if (p.mode === "walk_forward") parts.push("mode=WF");
  return parts.join(" ");
}

/* ---------- Cells ---------- */

function MetricNumCell({
  text,
  glyph,
}: {
  readonly text: string;
  readonly glyph: TrafficLight | null;
}) {
  return (
    <span className="inline-flex items-center font-mono">
      <span>{text}</span>
      {glyph && (
        <span className={`ml-1 ${GLYPH_CLASS[glyph]}`}>{GLYPH_CHAR[glyph]}</span>
      )}
    </span>
  );
}

/* ---------- Component ---------- */

export function RecentRunsTable({
  runs,
  baselineRunId,
  onRefill,
  onTogglePin,
  onSaveToZoo,
}: RecentRunsTableProps) {
  const { locale } = useLocale();
  const title = t(locale, "backtest.runs.title");

  if (runs.length === 0) {
    return (
      <TmPane title={title}>
        <div className="flex h-[80px] w-full items-center justify-center px-3 text-center font-tm-mono text-[11px] text-tm-muted">
          {t(locale, "backtest.runs.empty")}
        </div>
      </TmPane>
    );
  }

  // Newest first (already given by the hook). "Run #" descends: latest = runs.length.
  const total = runs.length;

  return (
    <TmPane title={title}>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-[11px]">
          <thead>
            <tr className="border-b border-tm-rule bg-tm-bg-2 font-tm-mono uppercase tracking-[0.04em] text-tm-muted">
              <th className="px-2 py-1 text-left font-semibold" style={{ width: "6ch" }}>
                {t(locale, "backtest.runs.colRun")}
              </th>
              <th
                className="px-1 py-1 text-center font-semibold"
                style={{ width: "2ch" }}
                aria-label={t(locale, "backtest.runs.baselineMark")}
              />
              <th className="px-2 py-1 text-right font-semibold" style={{ width: "8ch" }}>
                {t(locale, "backtest.wf.colSharpe")}
              </th>
              <th className="px-2 py-1 text-right font-semibold" style={{ width: "8ch" }}>
                {t(locale, "backtest.wf.colMdd")}
              </th>
              <th className="px-2 py-1 text-right font-semibold" style={{ width: "8ch" }}>
                {t(locale, "backtest.wf.colIc")}
              </th>
              <th className="px-2 py-1 text-right font-semibold" style={{ width: "6ch" }}>
                {t(locale, "backtest.runs.colTurnover")}
              </th>
              <th className="px-2 py-1 text-right font-semibold" style={{ width: "6ch" }}>
                {t(locale, "backtest.runs.colAnnRet")}
              </th>
              <th className="px-2 py-1 text-left font-semibold">
                {t(locale, "backtest.runs.colParams")}
              </th>
              <th
                className="px-2 py-1 text-right font-semibold"
                style={{ width: "12ch" }}
              >
                {t(locale, "backtest.runs.colActions")}
              </th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run, idx) => {
              const runNum = total - idx;
              const isPinned = run.id === baselineRunId;
              const m = run.metrics;
              const rowBgClass = isPinned
                ? "bg-tm-bg-3 hover:bg-tm-bg-3"
                : "hover:bg-tm-bg-3";
              return (
                <tr
                  key={run.id}
                  className={`border-b border-tm-rule font-tm-mono text-tm-fg ${rowBgClass}`}
                >
                  <td className="px-2 py-1 text-left font-mono text-tm-muted">
                    {runNum}
                  </td>
                  <td className="px-1 py-1 text-center">
                    {isPinned ? (
                      <Star
                        className="inline h-3 w-3 text-tm-accent"
                        strokeWidth={1.75}
                        fill="currentColor"
                        aria-label={t(locale, "backtest.runs.baselineMark")}
                      />
                    ) : (
                      <span aria-hidden="true">&nbsp;</span>
                    )}
                  </td>
                  <td className="px-2 py-1 text-right">
                    <MetricNumCell
                      text={fmtSharpe(m.sharpe)}
                      glyph={m.sharpe === null ? null : classifySharpe(m.sharpe)}
                    />
                  </td>
                  <td className="px-2 py-1 text-right">
                    <MetricNumCell
                      text={fmtMaxDD(m.maxDD)}
                      glyph={m.maxDD === null ? null : classifyMaxDD(m.maxDD)}
                    />
                  </td>
                  <td className="px-2 py-1 text-right">
                    <MetricNumCell
                      text={fmtIC(m.ic)}
                      glyph={m.ic === null ? null : classifyIC(m.ic)}
                    />
                  </td>
                  <td className="px-2 py-1 text-right font-mono">
                    {fmtTurnover(m.turnover)}
                  </td>
                  <td className="px-2 py-1 text-right font-mono">
                    {fmtAnnReturn(m.annReturn)}
                  </td>
                  <td className="px-2 py-1 text-left font-mono text-tm-fg-2">
                    {formatParamsSummary(run.params)}
                  </td>
                  <td className="px-2 py-1 text-right">
                    <div className="inline-flex items-center justify-end gap-1">
                      <button
                        type="button"
                        onClick={() => onRefill(run.id)}
                        aria-label={t(locale, "backtest.runs.refill")}
                        title={t(locale, "backtest.runs.refill")}
                        className="rounded p-1 text-tm-fg hover:bg-tm-bg-3"
                      >
                        <RotateCcw className="h-4 w-4" strokeWidth={1.75} />
                      </button>
                      <button
                        type="button"
                        onClick={() => onTogglePin(run.id)}
                        aria-label={t(locale, "backtest.runs.pin")}
                        aria-pressed={isPinned}
                        title={t(locale, "backtest.runs.pin")}
                        className="rounded p-1 text-tm-fg hover:bg-tm-bg-3"
                      >
                        <Star
                          className="h-4 w-4"
                          strokeWidth={1.75}
                          fill={isPinned ? "currentColor" : "none"}
                        />
                      </button>
                      <button
                        type="button"
                        onClick={() => onSaveToZoo(run.id)}
                        aria-label={t(locale, "backtest.runs.zoo")}
                        title={t(locale, "backtest.runs.zoo")}
                        className="rounded p-1 text-tm-fg hover:bg-tm-bg-3"
                      >
                        <Bookmark className="h-4 w-4" strokeWidth={1.75} />
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </TmPane>
  );
}
