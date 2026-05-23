"use client";

/**
 * RegimeBreakdownPane (T6) — bull / sideways / bear regime table.
 * Chart logic lifted from (dashboard)/backtest/page.tsx (lines 1091-1171).
 */

import { useLocale } from "@/components/layout/LocaleProvider";
import { t, type Locale } from "@/lib/i18n";
import { TmPane } from "@/components/tm/TmPane";
import type { FactorBacktestResponse } from "@/lib/types";
import type { Run } from "./types";

interface Props {
  readonly currentRun: Run | null;
}

type RegimeRowData = NonNullable<FactorBacktestResponse["regime_breakdown"]>[number];

function alphaTone(p: number, ts: number): string {
  if (p < 0.05 && ts > 0) return "text-tm-pos";
  if (p < 0.05 && ts < 0) return "text-tm-neg";
  if (p < 0.1 && ts > 0) return "text-tm-warn";
  return "text-tm-muted";
}

export function RegimeBreakdownPane({ currentRun }: Props) {
  const { locale } = useLocale();

  if (!currentRun) {
    return (
      <TmPane title="REGIME.BREAKDOWN">
        <UnavailableMessage text={t(locale, "backtest.evidence.waiting")} />
      </TmPane>
    );
  }

  const breakdown = currentRun.raw.regime_breakdown ?? [];
  if (breakdown.length === 0) {
    return (
      <TmPane title="REGIME.BREAKDOWN">
        <UnavailableMessage text={t(locale, "backtest.evidence.unavailable")} />
      </TmPane>
    );
  }

  return (
    <TmPane title="REGIME.BREAKDOWN" meta={`${breakdown.length} regimes`}>
      <p className="border-b border-tm-rule px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
        {t(locale, "backtest.regime.subtitle")}
      </p>
      <div className="overflow-x-auto">
        <div
          className="grid min-w-[700px] gap-px bg-tm-rule"
          style={{
            gridTemplateColumns:
              "minmax(120px,140px) 60px 60px 80px 70px 80px 60px 60px",
          }}
        >
          <RHeader>{t(locale, "backtest.regime.label")}</RHeader>
          <RHeader align="right">N</RHeader>
          <RHeader align="right">SR</RHeader>
          <RHeader align="right">IC</RHeader>
          <RHeader align="right">IC p</RHeader>
          <RHeader align="right">α (ann)</RHeader>
          <RHeader align="right">α-t</RHeader>
          <RHeader align="right">α p</RHeader>
          {breakdown.map((r) => (
            <RegimeRow
              key={r.regime}
              regime={r}
              tone={alphaTone(r.alpha_pvalue, r.alpha_t_stat)}
              locale={locale}
            />
          ))}
        </div>
      </div>
    </TmPane>
  );
}

function RegimeRow({
  regime: r,
  tone,
  locale,
}: {
  readonly regime: RegimeRowData;
  readonly tone: string;
  readonly locale: Locale;
}) {
  return (
    <>
      <RCell>
        <span className="text-tm-fg">
          {t(locale, `backtest.regime.${r.regime}` as Parameters<typeof t>[1])}
        </span>
      </RCell>
      <RCell align="right">
        <span className="tabular-nums text-tm-muted">{r.n_days}</span>
      </RCell>
      <RCell align="right">
        <span
          className={`tabular-nums ${r.sharpe >= 0 ? "text-tm-fg" : "text-tm-neg"}`}
        >
          {r.sharpe >= 0 ? "+" : ""}
          {r.sharpe.toFixed(2)}
        </span>
      </RCell>
      <RCell align="right">
        <span
          className={`tabular-nums ${r.ic_spearman >= 0 ? "text-tm-fg" : "text-tm-neg"}`}
        >
          {r.ic_spearman >= 0 ? "+" : ""}
          {r.ic_spearman.toFixed(4)}
        </span>
      </RCell>
      <RCell align="right">
        <span className="tabular-nums text-tm-muted">
          {r.ic_pvalue < 0.001 ? "<0.001" : r.ic_pvalue.toFixed(3)}
        </span>
      </RCell>
      <RCell align="right">
        <span className={`tabular-nums ${tone}`}>
          {r.alpha_annualized >= 0 ? "+" : ""}
          {(r.alpha_annualized * 100).toFixed(2)}%
        </span>
      </RCell>
      <RCell align="right">
        <span className={`tabular-nums ${tone}`}>
          {r.alpha_t_stat >= 0 ? "+" : ""}
          {r.alpha_t_stat.toFixed(2)}
        </span>
      </RCell>
      <RCell align="right">
        <span className={`tabular-nums ${tone}`}>
          {r.alpha_pvalue < 0.001 ? "<0.001" : r.alpha_pvalue.toFixed(3)}
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
