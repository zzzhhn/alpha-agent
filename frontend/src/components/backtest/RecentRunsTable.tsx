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
import { TmIconButton } from "@/components/tm/TmButton";
import { TmStatePane } from "@/components/tm/TmStatePane";
import {
  TmTable,
  TmTableBody,
  TmTableCell,
  TmTableFrame,
  TmTableHead,
  TmTableHeaderCell,
  TmTableRow,
  TmTableRowHeader,
} from "@/components/tm/TmTable";
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
        <TmStatePane
          state="empty"
          title={t(locale, "backtest.runs.empty")}
          className="min-h-20 rounded-none border-0"
        />
      </TmPane>
    );
  }

  // Newest first (already given by the hook). "Run #" descends: latest = runs.length.
  const total = runs.length;

  return (
    <TmPane title={title}>
      <TmTableFrame>
        <TmTable density="standard" caption={title} className="text-[11.5px]">
          <TmTableHead>
            <TmTableRow>
              <TmTableHeaderCell style={{ width: "6ch" }}>
                {t(locale, "backtest.runs.colRun")}
              </TmTableHeaderCell>
              <TmTableHeaderCell
                className="px-1"
                textAlign="center"
                style={{ width: "2ch" }}
                aria-label={t(locale, "backtest.runs.baselineMark")}
              />
              <TmTableHeaderCell textAlign="right" style={{ width: "8ch" }}>
                {t(locale, "backtest.wf.colSharpe")}
              </TmTableHeaderCell>
              <TmTableHeaderCell textAlign="right" style={{ width: "8ch" }}>
                {t(locale, "backtest.wf.colMdd")}
              </TmTableHeaderCell>
              <TmTableHeaderCell textAlign="right" style={{ width: "8ch" }}>
                {t(locale, "backtest.wf.colIc")}
              </TmTableHeaderCell>
              <TmTableHeaderCell textAlign="right" style={{ width: "6ch" }}>
                {t(locale, "backtest.runs.colTurnover")}
              </TmTableHeaderCell>
              <TmTableHeaderCell textAlign="right" style={{ width: "6ch" }}>
                {t(locale, "backtest.runs.colAnnRet")}
              </TmTableHeaderCell>
              <TmTableHeaderCell>
                {t(locale, "backtest.runs.colParams")}
              </TmTableHeaderCell>
              <TmTableHeaderCell
                textAlign="right"
                style={{ width: "12ch" }}
              >
                {t(locale, "backtest.runs.colActions")}
              </TmTableHeaderCell>
            </TmTableRow>
          </TmTableHead>
          <TmTableBody>
            {runs.map((run, idx) => {
              const runNum = total - idx;
              const isPinned = run.id === baselineRunId;
              const m = run.metrics;
              const rowBgClass = isPinned
                ? "bg-tm-bg-3 hover:bg-tm-bg-3"
                : "hover:bg-tm-bg-3";
              return (
                <TmTableRow
                  key={run.id}
                  className={`h-11 ${rowBgClass}`}
                >
                  <TmTableRowHeader className="px-2 font-normal text-tm-muted">
                    {runNum}
                  </TmTableRowHeader>
                  <TmTableCell className="px-1" textAlign="center">
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
                  </TmTableCell>
                  <TmTableCell numeric textAlign="right" className="px-2">
                    <MetricNumCell
                      text={fmtSharpe(m.sharpe)}
                      glyph={m.sharpe === null ? null : classifySharpe(m.sharpe)}
                    />
                  </TmTableCell>
                  <TmTableCell numeric textAlign="right" className="px-2">
                    <MetricNumCell
                      text={fmtMaxDD(m.maxDD)}
                      glyph={m.maxDD === null ? null : classifyMaxDD(m.maxDD)}
                    />
                  </TmTableCell>
                  <TmTableCell numeric textAlign="right" className="px-2">
                    <MetricNumCell
                      text={fmtIC(m.ic)}
                      glyph={m.ic === null ? null : classifyIC(m.ic)}
                    />
                  </TmTableCell>
                  <TmTableCell numeric textAlign="right" className="px-2">
                    {fmtTurnover(m.turnover)}
                  </TmTableCell>
                  <TmTableCell numeric textAlign="right" className="px-2">
                    {fmtAnnReturn(m.annReturn)}
                  </TmTableCell>
                  <TmTableCell className="px-2 text-tm-fg-2">
                    {formatParamsSummary(run.params)}
                  </TmTableCell>
                  <TmTableCell className="px-2" textAlign="right">
                    <div className="inline-flex items-center justify-end gap-1">
                      <TmIconButton
                        onClick={() => onRefill(run.id)}
                        label={t(locale, "backtest.runs.refill")}
                        icon={<RotateCcw className="h-4 w-4" strokeWidth={1.75} />}
                      />
                      <TmIconButton
                        onClick={() => onTogglePin(run.id)}
                        label={t(locale, "backtest.runs.pin")}
                        aria-pressed={isPinned}
                        icon={<Star
                          className="h-4 w-4"
                          strokeWidth={1.75}
                          fill={isPinned ? "currentColor" : "none"}
                        />}
                      />
                      <TmIconButton
                        onClick={() => onSaveToZoo(run.id)}
                        label={t(locale, "backtest.runs.zoo")}
                        icon={<Bookmark className="h-4 w-4" strokeWidth={1.75} />}
                      />
                    </div>
                  </TmTableCell>
                </TmTableRow>
              );
            })}
          </TmTableBody>
        </TmTable>
      </TmTableFrame>
    </TmPane>
  );
}
