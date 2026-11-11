import type { BrainAlpha, BrainMiningRun, BrainSubmitResult } from "@/lib/api/brain";
import type { Locale } from "@/lib/i18n";

/** Localize recognized diagnostics only; preserve the original for unknown text. */
export function translateBrainDiagnostic(line: string, locale: Locale): string {
  if (locale !== "zh") return line;
  // Screen diagnostics join independent facts with semicolons/newlines.
  return line.split(/(;\s*|\n)/).map((part) => {
    const rules: Array<[RegExp, string | ((match: RegExpMatchArray) => string)]> = [
      [/\b429\b|rate.?limit|too many requests/i, "请求过于频繁，已触发服务限流。"],
      [/GH_PAT not configured/i, "未配置 GitHub 派发凭据，无法启动挖矿。"],
      [/GitHub API (\d{3})/i, (m) => `GitHub 派发失败（HTTP ${m[1]}）。`],
      [/dispatch failed:/i, "GitHub Actions 任务派发失败，请检查连接与配置。"],
      [/no BRAIN credentials (?:configured|saved)/i, "尚未配置 BRAIN 账户凭据。"],
      [/credential load failed/i, "BRAIN 账户凭据读取失败。"],
      [/authentication failed|BrainAuthError|\b401\b|unauthorized/i, "BRAIN 身份验证失败，请检查账户凭据。"],
      [/unknown variable|unknown field|unrecognized variable/i, "表达式使用了 BRAIN 无法识别的变量或字段。"],
      [/logic screen.*(?:timed out|timeout)|logic.*screen.*TimeoutError/i, "逻辑预筛超时，请查看筛选状态及规则补位结果。"],
      [/logic screen failed|logic model unavailable|logic screen unavailable/i, "逻辑预筛不可用，请查看规则补位结果。"],
      [/no logic-screen LLM configured/i, "未配置逻辑预筛模型，使用规则筛选。"],
      [/scored (\d+)\/(\d+) expressions(?: in one full-pool call)?/i, (m) => `逻辑预筛已评分 ${m[1]}/${m[2]} 条表达式。`],
      [/partial scores retained/i, "已保留返回的部分评分。"],
      [/deterministic evidence screen selected (\d+)\/(\d+)/i, (m) => `规则证据筛选入选 ${m[1]}/${m[2]} 条。`],
      [/^selected (\d+)\/(\d+)$/i, (m) => `入选 ${m[1]}/${m[2]} 条。`],
      [/^withheld (\d+)/i, (m) => `未入选 ${m[1]} 条。`],
      [/candidate generation produced no usable expressions/i, "未生成可用表达式，本轮未提交 BRAIN 仿真。"],
      [/simulation .*timed out|simulation timeout|sim.*TimeoutError/i, "BRAIN 仿真等待超时，尚未取得完整结果。"],
      [/self.correlation near official limit/i, "自相关接近 BRAIN 官方门槛，需关注重复风险。"],
      [/high-quality-but-redundant|low marginal contribution/i, "绩效达标，但与已有因子重复或边际贡献不足。"],
      [/self[-_ ]corr(?:elation)?.*(?:FAIL|high|above|exceed)|SELF_CORRELATION.*FAIL/i, "自相关未通过门槛，与已有因子重合过高。"],
      [/family .* saturated|family-saturated/i, "该因子家族的代表名额已满。"],
      [/below in-sample gates/i, "未通过样本内绩效门槛（BRAIN 提交标准）。"],
      [/(?:LOW_FITNESS|fitness.*(?:below|low|FAIL))\b/i, "Fitness 未达到 BRAIN 门槛。"],
      [/(?:LOW_SHARPE|sharpe.*(?:below|low|FAIL))\b/i, "Sharpe 未达到 BRAIN 门槛。"],
      [/(?:LOW_TURNOVER|HIGH_TURNOVER|turnover.*(?:below|above|high|low|FAIL))\b/i, "换手率不符合 BRAIN 门槛。"],
      [/ConnectError|NetworkError|network error|connection (?:refused|reset)|RemoteProtocolError/i, "网络连接失败，请稍后重试。"],
      [/ReadTimeout|ConnectTimeout|read timed out/i, "网络请求超时，请稍后重试。"],
      [/simulate returned no Location\/sim_id|completed sim carried no alpha id/i, "BRAIN 返回结果缺少仿真或因子标识。"],
      [/simulate rejected:|simulation .*failed:/i, "BRAIN 未能完成该表达式的仿真，请查看原始日志。"],
    ];
    for (const [pattern, translation] of rules) {
      const match = part.match(pattern);
      if (match) return typeof translation === "function" ? translation(match) : translation;
    }
    return part;
  }).join("");
}

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
