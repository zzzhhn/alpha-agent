"use client";

import { AlertTriangle, CheckCircle2, HelpCircle, XCircle } from "lucide-react";
import { useLocale } from "@/components/layout/LocaleProvider";
import type { BacktestGateThresholds } from "@/lib/backtest-gates";
import type { Run } from "./types";

type CheckStatus = "pass" | "warn" | "fail" | "missing";
interface ValidationCheck {
  key: string;
  titleZh: string;
  titleEn: string;
  value: string;
  detailZh: string;
  detailEn: string;
  status: CheckStatus;
}

function buildChecks(run: Run, thresholds: BacktestGateThresholds): ValidationCheck[] {
  const { metrics, raw, params } = run;
  const samplePass = metrics.sharpe != null && metrics.maxDD != null && metrics.sharpe >= thresholds.sharpe && metrics.maxDD >= thresholds.maxDD;
  const sampleFail = (metrics.sharpe != null && metrics.sharpe < 0.5) || (metrics.maxDD != null && metrics.maxDD < -0.25);
  const windows = raw.walk_forward ?? [];
  const positiveWindows = windows.filter((w) => w.sharpe > 0 && w.ic_spearman > 0).length;
  const lastDay = raw.daily_breakdown?.at(-1);
  const weights = [...(lastDay?.long_basket ?? []), ...(lastDay?.short_basket ?? [])].map((item) => Math.abs(item.weight));
  const maxWeight = weights.length > 0 ? Math.max(...weights) : null;

  return [
    {
      key: "sample",
      titleZh: "样本外表现",
      titleEn: "Out-of-sample performance",
      value: metrics.sharpe == null ? "—" : `SR ${metrics.sharpe.toFixed(2)} · DD ${metrics.maxDD == null ? "—" : `${(metrics.maxDD * 100).toFixed(1)}%`}`,
      detailZh: `Sharpe ≥ ${thresholds.sharpe.toFixed(1)}，最大回撤 ≥ ${(thresholds.maxDD * 100).toFixed(0)}%`,
      detailEn: `Sharpe ≥ ${thresholds.sharpe.toFixed(1)}, max drawdown ≥ ${(thresholds.maxDD * 100).toFixed(0)}%`,
      status: samplePass ? "pass" : sampleFail ? "fail" : "warn",
    },
    {
      key: "walkforward",
      titleZh: "Walk-Forward 稳定性",
      titleEn: "Walk-forward stability",
      value: windows.length > 0 ? `${positiveWindows}/${windows.length}` : "—",
      detailZh: windows.length > 0 ? "正 Sharpe 且正 IC 的窗口占比" : "切换为 Walk-Forward 模式后可验证跨窗口稳定性",
      detailEn: windows.length > 0 ? "Windows with positive Sharpe and IC" : "Use Walk-forward mode to test stability across windows",
      status: windows.length === 0 ? "missing" : positiveWindows / windows.length >= 0.7 ? "pass" : positiveWindows / windows.length >= 0.5 ? "warn" : "fail",
    },
    {
      key: "cost",
      titleZh: "交易成本韧性",
      titleEn: "Transaction-cost robustness",
      value: `${params.transactionCostBps} bps`,
      detailZh: metrics.turnover == null ? "当前响应无换手率，无法判断成本侵蚀" : `当前为单一成本场景，换手率 ${(metrics.turnover * 100).toFixed(1)}%，尚未做敏感性扫描`,
      detailEn: metrics.turnover == null ? "Turnover unavailable; cost drag cannot be assessed" : `Single cost scenario; turnover ${(metrics.turnover * 100).toFixed(1)}%, no sensitivity sweep yet`,
      status: metrics.turnover == null ? "missing" : metrics.turnover > 0.6 ? "fail" : metrics.turnover > thresholds.turnover ? "warn" : "pass",
    },
    {
      key: "concentration",
      titleZh: "持仓集中度",
      titleEn: "Concentration check",
      value: maxWeight == null ? "—" : `${(maxWeight * 100).toFixed(1)}% max`,
      detailZh: maxWeight == null ? "开启“返回每日明细”后检查单一标的权重" : "单一标的绝对权重应低于 10%",
      detailEn: maxWeight == null ? "Enable daily breakdown to inspect position weights" : "Absolute weight per ticker should stay below 10%",
      status: maxWeight == null ? "missing" : maxWeight <= 0.1 ? "pass" : maxWeight <= 0.15 ? "warn" : "fail",
    },
    {
      key: "pit",
      titleZh: "前视与数据风险",
      titleEn: "Look-ahead and data risk",
      value: raw.survivorship_corrected ? "PIT" : "LEGACY",
      detailZh: raw.survivorship_corrected ? `已启用历史成分股掩码 · ${raw.membership_as_of ?? "按日"}` : "未确认历史成分股校正，结果可能含存活者偏差",
      detailEn: raw.survivorship_corrected ? `Point-in-time membership enabled · ${raw.membership_as_of ?? "daily"}` : "Point-in-time membership is unconfirmed; survivorship bias may remain",
      status: raw.survivorship_corrected ? "pass" : "warn",
    },
  ];
}

export function BacktestValidationGate({ currentRun, thresholds }: { readonly currentRun: Run | null; readonly thresholds: BacktestGateThresholds }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const checks = currentRun ? buildChecks(currentRun, thresholds) : [];
  const failed = checks.filter((check) => check.status === "fail").length;
  return (
    <section className="h-full border border-tm-rule bg-tm-bg">
      <div className="flex h-11 items-center justify-between border-b border-tm-rule bg-tm-bg-2/40 px-4">
        <span className="text-[12px] font-semibold tracking-[0.08em] text-tm-fg">{zh ? "验证门槛" : "Validation gates"}</span>
        <span className={`text-[10px] ${failed ? "text-tm-neg" : checks.length ? "text-tm-pos" : "text-tm-muted"}`}>{checks.length === 0 ? (zh ? "等待运行" : "Waiting") : failed ? (zh ? `${failed} 项反证` : `${failed} counter-evidence`) : (zh ? "未发现硬性反证" : "No hard counter-evidence")}</span>
      </div>
      {checks.length === 0 ? <div className="flex min-h-52 items-center justify-center px-4 text-center text-[10px] leading-5 text-tm-muted">{zh ? "运行回测后，这里会按稳健性问题逐项判断。" : "Run a backtest to evaluate robustness by decision question."}</div> : (
        <div className="divide-y divide-tm-rule">
          {checks.map((check) => {
            const Icon = check.status === "pass" ? CheckCircle2 : check.status === "fail" ? XCircle : check.status === "warn" ? AlertTriangle : HelpCircle;
            const tone = check.status === "pass" ? "text-tm-pos" : check.status === "fail" ? "text-tm-neg" : check.status === "warn" ? "text-tm-warn" : "text-tm-muted";
            return <div key={check.key} className="grid min-h-[62px] grid-cols-[28px_minmax(145px,0.9fr)_minmax(185px,1.2fr)] items-center gap-3 px-4 py-2 text-[10px]">
              <span className="flex h-6 w-6 items-center justify-center border border-tm-rule"><Icon className={`h-3.5 w-3.5 ${tone}`} /></span>
              <div><p className="text-tm-fg">{zh ? check.titleZh : check.titleEn}</p><p className={`mt-1 font-mono text-[11px] ${tone}`}>{check.value}</p></div>
              <p className="leading-4 text-tm-muted">{zh ? check.detailZh : check.detailEn}</p>
            </div>;
          })}
        </div>
      )}
      <p className="border-t border-tm-rule px-3 py-2 text-[9px] leading-4 text-tm-muted">{zh ? "缺失项会明确标记，不会被当作已通过。" : "Missing evidence is explicit and never treated as a pass."}</p>
    </section>
  );
}
