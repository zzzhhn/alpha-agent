"use client";

/**
 * TmTopBottomTable — workstation port of TopBottomTable.
 *
 * Renders today's long basket and short basket as two side-by-side
 * panes inside a TmCols2. Each side is a hairline grid (gap-px on
 * bg-tm-rule) so ranking + factor value + sector align across both
 * panes without nested tables. The top-level header strip uses the
 * standard TmPane title row with status meta (universe N / valid).
 *
 * Loading state is a thin placeholder bar; empty state is a centered
 * muted message. Both keep the pane height stable so the layout
 * doesn't reflow when results arrive.
 */

import { TmPane, TmCols2 } from "@/components/tm/TmPane";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import type { SignalTodayResponse } from "@/lib/types";

interface TmTopBottomTableProps {
  readonly today: SignalTodayResponse | null;
  readonly loading: boolean;
}

export function TmTopBottomTable({ today, loading }: TmTopBottomTableProps) {
  const { locale } = useLocale();
  const meta = today
    ? `AS_OF ${today.as_of} · ${today.n_valid}/${today.universe_size}`
    : undefined;

  if (loading && !today) {
    return (
      <TmPane title="SIGNAL.TODAY" meta="LOADING">
        <p className="px-3 py-6 text-center font-tm-mono text-[11px] text-tm-muted">
          …
        </p>
      </TmPane>
    );
  }
  if (!today) {
    return (
      <TmPane title="SIGNAL.TODAY">
        <p className="px-3 py-6 text-center font-tm-mono text-[11px] text-tm-muted">
          {t(locale, "signal.today.empty")}
        </p>
      </TmPane>
    );
  }

  return (
    <TmPane title="SIGNAL.TODAY" meta={meta}>
      <TmCols2>
        <BasketSide
          title={t(locale, "signal.today.long")}
          rows={today.top}
          tone="pos"
        />
        <BasketSide
          title={t(locale, "signal.today.short")}
          rows={today.bottom}
          tone="neg"
        />
      </TmCols2>
    </TmPane>
  );
}

function BasketSide({
  title,
  rows,
  tone,
}: {
  readonly title: string;
  readonly rows: SignalTodayResponse["top"];
  readonly tone: "pos" | "neg";
}) {
  const { locale } = useLocale();
  const accentClass = tone === "pos" ? "text-tm-pos" : "text-tm-neg";
  return (
    <div className="flex flex-col">
      <div className="flex items-center justify-between border-b border-tm-rule bg-tm-bg-2 px-3 py-1.5 font-tm-mono text-[10.5px]">
        <span className={`font-semibold uppercase tracking-[0.06em] ${accentClass}`}>
          {title}
        </span>
        <span className="text-tm-muted">{rows.length} TICKERS</span>
      </div>
      <div
        className="grid gap-px bg-tm-rule"
        style={{ gridTemplateColumns: "32px 1fr minmax(80px, 100px) 1fr" }}
      >
        <HeaderCell>#</HeaderCell>
        <HeaderCell>{t(locale, "signal.today.tickerCol")}</HeaderCell>
        <HeaderCell align="right">{t(locale, "signal.today.factorVal")}</HeaderCell>
        <HeaderCell>{t(locale, "signal.today.sectorCol")}</HeaderCell>
        {rows.map((r, i) => (
          <RankRow
            key={r.ticker}
            rank={i + 1}
            ticker={r.ticker}
            factor={r.factor}
            sector={r.sector ?? null}
            tone={accentClass}
          />
        ))}
      </div>
    </div>
  );
}

function HeaderCell({
  children,
  align = "left",
}: {
  readonly children: React.ReactNode;
  readonly align?: "left" | "right";
}) {
  return (
    <div
      className={`bg-tm-bg-2 px-2 py-1 font-tm-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-tm-muted ${
        align === "right" ? "text-right" : ""
      }`}
    >
      {children}
    </div>
  );
}

function RankRow({
  rank,
  ticker,
  factor,
  sector,
  tone,
}: {
  readonly rank: number;
  readonly ticker: string;
  readonly factor: number;
  readonly sector: string | null;
  readonly tone: string;
}) {
  return (
    <>
      <div className="bg-tm-bg px-2 py-1 font-tm-mono text-[10.5px] text-tm-muted">
        {String(rank).padStart(2, "0")}
      </div>
      <div className={`bg-tm-bg px-2 py-1 font-tm-mono text-[11.5px] font-semibold ${tone}`}>
        {ticker}
      </div>
      <div className="bg-tm-bg px-2 py-1 text-right font-tm-mono text-[11px] tabular-nums text-tm-fg">
        {factor.toFixed(3)}
      </div>
      <div className="bg-tm-bg px-2 py-1 font-tm-mono text-[10.5px] text-tm-fg-2">
        {sector ?? "—"}
      </div>
    </>
  );
}
