"use client";

/**
 * DailyBreakdownPane (T6) — tail-30 daily detail + CSV download.
 * Chart logic lifted from (dashboard)/backtest/page.tsx (lines 1249-1344).
 *
 * Requires `daily_breakdown` on the response.
 */

import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { TmPane } from "@/components/tm/TmPane";
import type { FactorBacktestResponse } from "@/lib/types";
import type { Run } from "./types";

interface Props {
  readonly currentRun: Run | null;
}

export function DailyBreakdownPane({ currentRun }: Props) {
  const { locale } = useLocale();

  if (!currentRun) {
    return (
      <TmPane title="DAILY.BREAKDOWN">
        <UnavailableMessage text={t(locale, "backtest.evidence.waiting")} />
      </TmPane>
    );
  }

  const breakdown = currentRun.raw.daily_breakdown;
  const factorName = currentRun.raw.factor_name;
  if (!breakdown || breakdown.length === 0) {
    return (
      <TmPane title="DAILY.BREAKDOWN">
        <UnavailableMessage text={t(locale, "backtest.evidence.unavailable")} />
      </TmPane>
    );
  }

  const populated = breakdown.filter(
    (d) => d.long_basket.length > 0 || d.short_basket.length > 0,
  );
  const positiveIc = populated.filter((d) => d.daily_ic > 0).length;
  const hitRate = populated.length > 0 ? positiveIc / populated.length : 0;

  function downloadFlat() {
    const rows: string[][] = [];
    rows.push(["date", "side", "ticker", "weight", "daily_return", "daily_ic"]);
    for (const d of breakdown ?? []) {
      for (const e of d.long_basket) {
        rows.push([
          d.date,
          "long",
          e.ticker,
          e.weight.toFixed(6),
          d.daily_return.toFixed(6),
          d.daily_ic.toFixed(6),
        ]);
      }
      for (const e of d.short_basket) {
        rows.push([
          d.date,
          "short",
          e.ticker,
          e.weight.toFixed(6),
          d.daily_return.toFixed(6),
          d.daily_ic.toFixed(6),
        ]);
      }
    }
    const csv = rows
      .map((r) => r.map((c) => `"${c.replace(/"/g, '""')}"`).join(","))
      .join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${factorName}_daily_breakdown.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <TmPane
      title="DAILY.BREAKDOWN"
      meta={`${populated.length} sessions · hit ${(hitRate * 100).toFixed(0)}%`}
    >
      <div className="flex items-center justify-between border-b border-tm-rule bg-tm-bg-2 px-3 py-1.5">
        <span className="font-tm-mono text-[10.5px] text-tm-muted">
          {t(locale, "backtest.breakdown.subtitle")
            .replace("{n}", String(populated.length))
            .replace("{hit}", `${(hitRate * 100).toFixed(0)}%`)}
        </span>
        <button
          type="button"
          onClick={downloadFlat}
          className="font-tm-mono text-[10px] uppercase tracking-[0.06em] text-tm-muted hover:text-tm-accent"
        >
          {t(locale, "backtest.breakdown.download")}
        </button>
      </div>
      <div className="overflow-x-auto">
        <div
          className="grid min-w-[860px] gap-px bg-tm-rule"
          style={{
            gridTemplateColumns:
              "minmax(110px,130px) 60px 60px 70px 70px 1fr 1fr",
          }}
        >
          <RHeader>{t(locale, "backtest.breakdown.colDate")}</RHeader>
          <RHeader align="right">
            {t(locale, "backtest.breakdown.colNLong")}
          </RHeader>
          <RHeader align="right">
            {t(locale, "backtest.breakdown.colNShort")}
          </RHeader>
          <RHeader align="right">
            {t(locale, "backtest.breakdown.colReturn")}
          </RHeader>
          <RHeader align="right">
            {t(locale, "backtest.breakdown.colIc")}
          </RHeader>
          <RHeader>{t(locale, "backtest.breakdown.colTopLong")}</RHeader>
          <RHeader>{t(locale, "backtest.breakdown.colTopShort")}</RHeader>
          {populated
            .slice(-30)
            .reverse()
            .map((d) => (
              <BreakdownRow key={d.date} row={d} />
            ))}
        </div>
      </div>
      <p className="border-t border-tm-rule px-3 py-1.5 font-tm-mono text-[10px] leading-relaxed text-tm-muted">
        {t(locale, "backtest.breakdown.tableHint")}
      </p>
    </TmPane>
  );
}

function BreakdownRow({
  row: d,
}: {
  readonly row: NonNullable<FactorBacktestResponse["daily_breakdown"]>[number];
}) {
  return (
    <>
      <RCell>
        <span className="font-tm-mono text-tm-fg">{d.date}</span>
      </RCell>
      <RCell align="right">
        <span className="tabular-nums text-tm-muted">
          {d.long_basket.length}
        </span>
      </RCell>
      <RCell align="right">
        <span className="tabular-nums text-tm-muted">
          {d.short_basket.length}
        </span>
      </RCell>
      <RCell align="right">
        <span
          className={`tabular-nums ${d.daily_return >= 0 ? "text-tm-pos" : "text-tm-neg"}`}
        >
          {(d.daily_return * 100).toFixed(2)}%
        </span>
      </RCell>
      <RCell align="right">
        <span
          className={`tabular-nums ${d.daily_ic >= 0 ? "text-tm-pos" : "text-tm-neg"}`}
        >
          {d.daily_ic.toFixed(3)}
        </span>
      </RCell>
      <RCell>
        <span className="truncate text-tm-muted">
          {d.long_basket
            .slice(0, 3)
            .map((e) => e.ticker)
            .join(", ")}
        </span>
      </RCell>
      <RCell>
        <span className="truncate text-tm-muted">
          {d.short_basket
            .slice(0, 3)
            .map((e) => e.ticker)
            .join(", ")}
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
