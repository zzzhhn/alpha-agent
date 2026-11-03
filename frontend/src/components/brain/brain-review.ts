import type { BrainAlpha, BrainMiningRun, BrainSubmitResult } from "@/lib/api/brain";

export type BrainSubmissionState = "accepted" | "rejected" | "attempted";

export function brainSubmissionState(
  receipt: Pick<BrainSubmitResult, "ok"> | Pick<BrainAlpha, "submitted_at" | "brain_status">,
): BrainSubmissionState | null {
  if ("ok" in receipt) return receipt.ok ? "accepted" : "rejected";
  if (!receipt.submitted_at) return null;
  const status = receipt.brain_status?.toLowerCase();
  if (status === "submit_rejected") return "rejected";
  if (status === "submitted" || status === "active") return "accepted";
  return "attempted";
}

const FAMILIES: Record<string, [string, string]> = {
  value: ["价值", "Value"],
  dispersion: ["分歧度", "Dispersion"],
  microstructure: ["微观结构", "Microstructure"],
  seasonality: ["季节性", "Seasonality"],
  overnight: ["隔夜", "Overnight"],
  iv_term: ["隐波期限结构", "IV term"],
  iv_skew_dynamics: ["隐波偏斜变化", "IV skew dynamics"],
  iv_momentum: ["隐波动量", "IV momentum"],
  pcr_dynamics: ["认沽认购比变化", "PCR dynamics"],
  option_breakeven: ["期权盈亏平衡", "Option breakeven"],
  vrp: ["波动率风险溢价", "VRP"],
  quality: ["质量", "Quality"],
  options: ["期权多机制", "Options multi-mechanism"],
  lowvol: ["低波动", "Low volatility"],
  sentiment: ["情绪", "Sentiment"],
  momentum: ["动量", "Momentum"],
  score: ["因子评分", "Factor score"],
  revision: ["预期修正", "Revision"],
  other: ["其他", "Other"],
  frontier: ["前沿结构", "Frontier"],
  composite: ["跨机制复合", "Composite"],
  blend: ["拼接", "Blend"],
  mixed: ["混合家族", "Mixed family"],
};

export const DEFAULT_BRAIN_PAGE_SIZE = 10;

export function familyLabel(value: string | null | undefined, zh: boolean): string {
  const key = value || "mixed";
  return FAMILIES[key]?.[zh ? 0 : 1] ?? key;
}

export function hasUnsimulatedCandidates(run: BrainMiningRun | null): boolean {
  return (run?.generated_n ?? 0) > 0 && run?.simulated_n === 0;
}

export function nextExpandedAlpha(current: number | null, clicked: number): number | null {
  return current === clicked ? null : clicked;
}

export function runFailureAction(run: BrainMiningRun, zh: boolean): string {
  const error = run.error_detail ?? "";
  if (/GH_PAT not configured|dispatch failed:|GitHub API \d{3}/i.test(error)) {
    return zh
      ? "挖矿任务未能派发。请先检查 GitHub Actions 的派发配置，再载入本轮参数重试。"
      : "The run could not be dispatched. Check the GitHub Actions dispatch setup before reusing its settings.";
  }
  if (run.generated_n === 0 && run.persisted_n === 0) {
    return zh
      ? "本轮没有生成候选。请查看运行诊断，确认生成配置后再重试。"
      : "No candidates were generated. Check Run diagnostics and the generation setup before retrying.";
  }
  return zh
    ? "本轮未正常完成。请先查看运行诊断，再决定是否载入参数重试。"
    : "The run did not finish normally. Check Run diagnostics before reusing its settings.";
}
