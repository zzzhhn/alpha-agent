"use client";

/**
 * RiskAttributionPane (T6) — α / β / R² verdict from full-period OLS regression
 * against benchmark. Chart logic lifted from (dashboard)/backtest/page.tsx
 * (lines 305-344).
 */

import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { TmPane } from "@/components/tm/TmPane";
import { TmKpi, TmKpiGrid } from "@/components/tm/TmKpi";
import type { Run } from "./types";

interface Props {
  readonly currentRun: Run | null;
}

export function RiskAttributionPane({ currentRun }: Props) {
  const { locale } = useLocale();

  if (!currentRun) {
    return (
      <TmPane title="RISK.ATTRIBUTION">
        <UnavailableMessage
          text={t(locale, "backtest.evidence.waiting")}
        />
      </TmPane>
    );
  }

  const result = currentRun.raw;
  const alpha = result.alpha_annualized ?? 0;
  const beta = result.beta_market ?? 0;
  const r2 = result.r_squared ?? 0;
  const pAlpha = result.alpha_pvalue ?? 1;

  const alphaTone: "pos" | "neg" | "warn" | "default" =
    pAlpha < 0.05 && alpha > 0
      ? "pos"
      : pAlpha < 0.05 && alpha < 0
        ? "neg"
        : pAlpha < 0.1 && alpha > 0
          ? "warn"
          : "default";

  const verdict =
    pAlpha < 0.05 && Math.abs(beta) < 0.3
      ? t(locale, "backtest.risk.verdictAlphaPure")
      : pAlpha < 0.05
        ? t(locale, "backtest.risk.verdictAlphaLevered")
        : pAlpha < 0.1 && alpha > 0 && Math.abs(beta) < 0.3
          ? t(locale, "backtest.risk.verdictMarginal")
          : Math.abs(beta) > 0.5
            ? t(locale, "backtest.risk.verdictBetaOnly")
            : t(locale, "backtest.risk.verdictNoise");

  return (
    <TmPane title="RISK.ATTRIBUTION" meta="α / β / R² / verdict">
      <p className="border-b border-tm-rule px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
        {t(locale, "backtest.risk.subtitle")}
      </p>
      <TmKpiGrid>
        <TmKpi
          label={t(locale, "backtest.risk.alpha")}
          value={`${alpha >= 0 ? "+" : ""}${(alpha * 100).toFixed(2)}%`}
          tone={alphaTone}
          sub={`p=${pAlpha < 0.001 ? "<0.001" : pAlpha.toFixed(3)}`}
        />
        <TmKpi
          label={t(locale, "backtest.risk.beta")}
          value={`${beta >= 0 ? "+" : ""}${beta.toFixed(3)}`}
          tone={Math.abs(beta) > 0.5 ? "warn" : "default"}
          sub={t(locale, "backtest.risk.betaHint")}
        />
        <TmKpi
          label="R²"
          value={`${(r2 * 100).toFixed(1)}%`}
          sub={t(locale, "backtest.risk.r2Hint")}
        />
        <TmKpi
          label={t(locale, "backtest.risk.verdict")}
          value={verdict}
          tone={alphaTone}
        />
      </TmKpiGrid>
    </TmPane>
  );
}

function UnavailableMessage({ text }: { readonly text: string }) {
  return (
    <div className="flex h-[120px] w-full items-center justify-center px-3 text-center font-tm-mono text-[11px] text-tm-muted">
      {text}
    </div>
  );
}
