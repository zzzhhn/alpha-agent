"use client";

import { AlertCircle, Check, Loader2 } from "lucide-react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { DecisionStrip } from "@/components/workbench/DecisionStrip";
import { TmButton } from "@/components/tm/TmButton";
import { t } from "@/lib/i18n";
import type { ChainState, ThresholdEval, VerdictMetrics } from "./types";

interface Props {
  state: ChainState;
  metrics: VerdictMetrics;
  thresholds: ThresholdEval;
  canSave: boolean;
  onSave: () => void;
  onReTranslate: () => void;
}

export function VerdictBar({ state, metrics, thresholds, canSave, onSave, onReTranslate }: Props) {
  const { locale } = useLocale();
  const zh = locale === "zh";

  const available = [metrics.ic, metrics.sharpe, metrics.maxDrawdown].filter((value) => value !== null).length;
  const failed = [thresholds.ic, thresholds.sharpe, thresholds.maxDrawdown].filter((item) => item?.status === "bad").length;
  const warning = [thresholds.ic, thresholds.sharpe, thresholds.maxDrawdown].filter((item) => item?.status === "warn").length;
  const overallTone = failed > 0 ? "negative" : warning > 0 ? "warning" : available === 3 ? "positive" : "default";
  const overall = state.kind === "idle"
    ? (zh ? "等待验证" : "Awaiting validation")
    : state.kind === "translating"
      ? (zh ? "正在生成可检验表达式" : "Building a testable expression")
      : state.kind === "backtesting"
        ? (zh ? "正在寻找样本外反证" : "Searching for out-of-sample counter-evidence")
        : failed > 0
          ? (zh ? `${failed} 项门槛形成反证` : `${failed} gates provide counter-evidence`)
          : warning > 0
            ? (zh ? `${warning} 项门槛需要复核` : `${warning} gates need review`)
            : available === 3
              ? (zh ? "关键门槛通过，候选可进入比较" : "Key gates pass; candidate can enter comparison")
              : (zh ? "部分证据可用" : "Partial evidence available");

  if (state.kind === "idle") {
    return (
      <DecisionStrip
        headline={<><span className="mr-2 text-tm-accent">②</span>{overall}</>}
        description={t(locale, "alpha.verdict.idle" as Parameters<typeof t>[1])}
        metrics={[
          { label: "IC", value: "—", detail: zh ? "阈值在结果中显示" : "Threshold shown with result" },
          { label: "Sharpe", value: "—", detail: zh ? "等待回测" : "Waiting for backtest" },
          { label: "MaxDD", value: "—", detail: zh ? "等待回测" : "Waiting for backtest" },
          { label: zh ? "证据完整度" : "Evidence", value: "0 / 3" },
        ]}
      />
    );
  }

  if (state.kind === "translate_error") {
    return (
      <section className="flex items-center justify-between border-b border-tm-neg/40 bg-tm-neg/10 px-6 py-4">
        <div className="flex items-center gap-2 font-tm-mono text-sm text-tm-neg">
          <AlertCircle className="h-4 w-4 shrink-0" strokeWidth={1.75} />
          <span>
            {t(locale, "alpha.verdict.translateFailed" as Parameters<typeof t>[1])}
            {state.message}
          </span>
        </div>
        <TmButton
          variant="danger"
          size="sm"
          onClick={onReTranslate}
        >
          {t(locale, "alpha.verdict.retranslate" as Parameters<typeof t>[1])}
        </TmButton>
      </section>
    );
  }

  return (
    <DecisionStrip
      headline={(
        <span className="inline-flex items-center gap-2">
          <span className="text-tm-accent">②</span>
          {(state.kind === "translating" || state.kind === "backtesting") ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          {overall}
        </span>
      )}
      description={state.kind === "backtest_error"
        ? `${t(locale, "alpha.backtest.errorPrefix" as Parameters<typeof t>[1])}${state.message.slice(0, 100)}`
        : (zh ? "原值与门槛并列，任何一项反证都不会被综合分掩盖。" : "Raw values sit beside thresholds; no composite score hides counter-evidence.")}
      metrics={[
        { label: "IC (20D)", value: metrics.ic === null ? "—" : `${metrics.ic >= 0 ? "+" : ""}${metrics.ic.toFixed(4)}`, detail: thresholds.ic?.threshold, tone: thresholds.ic?.status === "bad" ? "negative" : thresholds.ic?.status === "warn" ? "warning" : metrics.ic === null ? "default" : "positive" },
        { label: "Sharpe", value: metrics.sharpe === null ? "—" : metrics.sharpe.toFixed(2), detail: thresholds.sharpe?.threshold, tone: thresholds.sharpe?.status === "bad" ? "negative" : thresholds.sharpe?.status === "warn" ? "warning" : metrics.sharpe === null ? "default" : "positive" },
        { label: "MaxDD", value: metrics.maxDrawdown === null ? "—" : `${(metrics.maxDrawdown * 100).toFixed(1)}%`, detail: thresholds.maxDrawdown?.threshold, tone: thresholds.maxDrawdown?.status === "bad" ? "negative" : thresholds.maxDrawdown?.status === "warn" ? "warning" : metrics.maxDrawdown === null ? "default" : "positive" },
        { label: zh ? "证据完整度" : "Evidence", value: `${available} / 3`, detail: zh ? "服务端结果" : "Server result", tone: overallTone },
      ]}
      action={canSave ? (
        <TmButton
          variant="primary"
          size="sm"
          onClick={onSave}
          aria-label={t(locale, "alpha.verdict.saveToZoo" as Parameters<typeof t>[1])}
        >
          <Check className="h-3.5 w-3.5" strokeWidth={1.75} />
          {t(locale, "alpha.verdict.saveToZoo" as Parameters<typeof t>[1])}
        </TmButton>
      ) : undefined}
    />
  );
}
