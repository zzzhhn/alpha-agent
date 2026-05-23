"use client";

/**
 * WorstDrawdownsPane (T6) — top-5 peak-to-trough drawdown periods table.
 * Chart logic lifted from (dashboard)/backtest/page.tsx (lines 445-577).
 */

import { useMemo } from "react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { TmPane } from "@/components/tm/TmPane";
import type { EquityCurvePoint } from "@/lib/types";
import type { Run } from "./types";

interface Props {
  readonly currentRun: Run | null;
}

interface DrawdownPeriod {
  readonly start: string;
  readonly trough: string;
  readonly recovery: string | null;
  readonly depth: number;
  readonly durationDays: number;
  readonly recoveryDays: number | null;
}

function findDrawdowns(eq: readonly EquityCurvePoint[]): DrawdownPeriod[] {
  if (eq.length === 0) return [];
  const out: DrawdownPeriod[] = [];
  let peak = eq[0].value;
  let peakDate = eq[0].date;
  let inDD = false;
  let troughVal = peak;
  let troughDate = peakDate;
  for (let i = 1; i < eq.length; i++) {
    const p = eq[i];
    if (p.value >= peak) {
      if (inDD) {
        const depth = (troughVal - peak) / peak;
        const durationDays = i - eq.findIndex((x) => x.date === peakDate);
        const troughIdx = eq.findIndex((x) => x.date === troughDate);
        const recoveryDays = i - troughIdx;
        out.push({
          start: peakDate,
          trough: troughDate,
          recovery: p.date,
          depth,
          durationDays,
          recoveryDays,
        });
        inDD = false;
      }
      peak = p.value;
      peakDate = p.date;
      troughVal = peak;
      troughDate = p.date;
    } else {
      if (!inDD) {
        inDD = true;
        troughVal = p.value;
        troughDate = p.date;
      } else if (p.value < troughVal) {
        troughVal = p.value;
        troughDate = p.date;
      }
    }
  }
  if (inDD) {
    const depth = (troughVal - peak) / peak;
    const peakIdx = eq.findIndex((x) => x.date === peakDate);
    const durationDays = eq.length - 1 - peakIdx;
    out.push({
      start: peakDate,
      trough: troughDate,
      recovery: null,
      depth,
      durationDays,
      recoveryDays: null,
    });
  }
  return out.sort((a, b) => a.depth - b.depth).slice(0, 5);
}

export function WorstDrawdownsPane({ currentRun }: Props) {
  const { locale } = useLocale();
  const periods = useMemo(
    () => (currentRun ? findDrawdowns(currentRun.raw.equity_curve) : []),
    [currentRun],
  );

  if (!currentRun) {
    return (
      <TmPane title="WORST.DRAWDOWNS">
        <UnavailableMessage text={t(locale, "backtest.evidence.waiting")} />
      </TmPane>
    );
  }
  if (periods.length === 0) {
    return (
      <TmPane title="WORST.DRAWDOWNS">
        <UnavailableMessage text={t(locale, "backtest.evidence.unavailable")} />
      </TmPane>
    );
  }

  const worstDepth = periods[0]?.depth ?? 0;
  return (
    <TmPane
      title="WORST.DRAWDOWNS"
      meta={`top ${periods.length} · worst ${(worstDepth * 100).toFixed(1)}%`}
    >
      <p className="border-b border-tm-rule px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
        {t(locale, "backtest.worstDD.subtitle" as Parameters<typeof t>[1])}
      </p>
      <div className="overflow-x-auto">
        <div
          className="grid min-w-[760px] gap-px bg-tm-rule"
          style={{
            gridTemplateColumns:
              "32px minmax(120px,140px) minmax(120px,140px) minmax(120px,140px) 80px 80px 80px",
          }}
        >
          <RHeader>#</RHeader>
          <RHeader>{t(locale, "backtest.worstDD.colStart" as Parameters<typeof t>[1])}</RHeader>
          <RHeader>{t(locale, "backtest.worstDD.colTrough" as Parameters<typeof t>[1])}</RHeader>
          <RHeader>{t(locale, "backtest.worstDD.colRecovery" as Parameters<typeof t>[1])}</RHeader>
          <RHeader align="right">
            {t(locale, "backtest.worstDD.colDepth" as Parameters<typeof t>[1])}
          </RHeader>
          <RHeader align="right">
            {t(locale, "backtest.worstDD.colDuration" as Parameters<typeof t>[1])}
          </RHeader>
          <RHeader align="right">
            {t(locale, "backtest.worstDD.colRecoveryDays" as Parameters<typeof t>[1])}
          </RHeader>
          {periods.map((p, i) => (
            <DDRow
              key={`${p.start}-${p.trough}`}
              rank={i + 1}
              dd={p}
              ongoingLabel={t(locale, "backtest.worstDD.ongoing" as Parameters<typeof t>[1])}
            />
          ))}
        </div>
      </div>
    </TmPane>
  );
}

function DDRow({
  rank,
  dd,
  ongoingLabel,
}: {
  readonly rank: number;
  readonly dd: DrawdownPeriod;
  readonly ongoingLabel: string;
}) {
  return (
    <>
      <RCell>
        <span className="text-tm-muted">{String(rank).padStart(2, "0")}</span>
      </RCell>
      <RCell>
        <span className="text-tm-fg">{dd.start}</span>
      </RCell>
      <RCell>
        <span className="text-tm-neg">{dd.trough}</span>
      </RCell>
      <RCell>
        <span className={dd.recovery === null ? "text-tm-warn" : "text-tm-pos"}>
          {dd.recovery ?? ongoingLabel}
        </span>
      </RCell>
      <RCell align="right">
        <span className="tabular-nums text-tm-neg">
          {(dd.depth * 100).toFixed(1)}%
        </span>
      </RCell>
      <RCell align="right">
        <span className="tabular-nums text-tm-fg-2">{dd.durationDays}d</span>
      </RCell>
      <RCell align="right">
        <span className="tabular-nums text-tm-fg-2">
          {dd.recoveryDays !== null ? `${dd.recoveryDays}d` : "—"}
        </span>
      </RCell>
    </>
  );
}

function RHeader({
  children,
  align = "left",
}: {
  readonly children: React.ReactNode;
  readonly align?: "left" | "right";
}) {
  return (
    <div
      className={`bg-tm-bg-2 px-2 py-1.5 font-tm-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-tm-muted ${
        align === "right" ? "text-right" : ""
      }`}
    >
      {children}
    </div>
  );
}

function RCell({
  children,
  align = "left",
}: {
  readonly children: React.ReactNode;
  readonly align?: "left" | "right";
}) {
  return (
    <div
      className={`flex min-w-0 items-center bg-tm-bg px-2 py-1 font-tm-mono text-[11px] ${
        align === "right" ? "justify-end" : ""
      }`}
    >
      {children}
    </div>
  );
}

function UnavailableMessage({ text }: { readonly text: string }) {
  return (
    <div className="flex h-[120px] w-full items-center justify-center px-3 text-center font-tm-mono text-[11px] text-tm-muted">
      {text}
    </div>
  );
}
