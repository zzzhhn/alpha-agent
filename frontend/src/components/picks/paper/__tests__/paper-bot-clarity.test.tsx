import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import type { PaperBotPerformance, PaperBotRun } from "@/lib/api/paper-bot";
import {
  PaperBotActions, PaperBotDecisionSummary, PaperBotExecutionSummary,
  botOutcomeLabel, botRunLabel, botTime, botZoneLabel, botZonedTime, humanizeBotText,
} from "../PaperBotUi";
import { PaperBotPerformanceSummary, botSampleLength } from "../PaperBotEvidence";

const run: PaperBotRun = {
  id: "clarity-run", account_id: 7, status: "completed", stage: "valuing", trigger: "manual",
  created_at: "2026-11-06T15:05:00Z", started_at: "2026-11-06T15:05:00Z", finished_at: "2026-11-06T15:06:00Z",
  summary: "keep_positions；target_weight=0.2；research_run_id=78。", error: null,
  result: { outcome_reason: "orders_settled", actions: [{
    action_id: "a1", ticker: "TEST", status: "accepted", order_status: "filled",
    filled_at: "2026-11-06T15:05:00Z", filled_price: 10, fee: 0.05, evidence_ids: ["rating:1"],
  }] },
  prompt_tokens: null, completion_tokens: null, provider: null, model: null,
  order_summary: { total: 1, filled: 1, pending: 0, failed: 0, expired: 0, cancelled: 0, filled_notional: 100, paid_fees: 0.05 },
};

const performance: PaperBotPerformance = {
  account_id: 7, cohort_id: 1, as_of: "2026-11-06T15:05:00Z",
  history: { scope: "current_cohort_recent_366", sample_count: 20, valid_nav_count: 20, null_nav_count: 0, first_date: "2026-10-09", last_date: "2026-11-06", truncated: false },
  valuation: { cash: 1000, portfolio_value: 1100, invested_value: 100, exposure_pct: 9.09, quality: "fresh", valued_at: "2026-11-06T15:05:00Z" },
  matched_window: { start_date: "2026-10-09", end_date: "2026-11-06", sample_count: 19, expected_sessions: 20, missing_sessions: 1, complete: false, bot_return_pct: 1.2, spy_return_pct: 0.5, cash_return_pct: 0, bot_max_drawdown_pct: null, reason: "incomplete_daily_path" },
  orders: { scope: "current_cohort", filled: 2, pending: 0, failed: 0, expired: 0, cancelled: 0, paid_fees: 1.25 },
  turnover: { window_start: null, window_end: null, gross_filled_notional: null, average_nav: null, ratio_pct: null, reason: "insufficient_common_observations" },
  llm: { scope: "recent_20_runs_account_lifetime", run_count: 2, prompt_tokens: null, completion_tokens: null, cost_usd: null, cost_reason: "provider_pricing_unavailable" },
  comparators: { spy: { basis: "raw_price_no_dividends" }, cash: { basis: "zero_interest" }, deterministic: { available: false, reason: "no_simulated_ledger" } },
};

describe("paper bot clarity", () => {
  it.each([
    ["keep_positions", "保留现有持仓", "Keep positions"],
    ["keep_cash", "保留现金", "Keep cash"],
    ["target_weight", "目标权重", "Target weight"],
    ["max_positions", "最多持仓数", "Maximum positions"],
    ["max_position_weight", "单一标的最高权重", "Maximum position weight"],
    ["horizon_sessions", "决策期限（交易日）", "Decision horizon (sessions)"],
    ["research_run_id", "研究批次", "Research run"],
    ["evidence_ids", "证据编号", "Evidence IDs"],
    ["top_n", "前 N 名", "Top N"],
    ["held_outside_top_n", "前 N 名之外的持仓", "Holdings outside top N"],
    ["rebalance", "调仓", "Rebalance"],
    ["no_trade_reason", "不交易原因", "No-trade reason"],
  ])("humanizes %s in both locales", (token, zh, en) => {
    expect(humanizeBotText(`采用${token}；${token}=0.25`, "zh")).toBe(`采用${zh}；${zh}=0.25`);
    expect(humanizeBotText(`${token}: 0.25`, "en")).toBe(`${en}: 0.25`);
  });

  it("preserves numbers, unknown words and longer identifiers", () => {
    const text = "max_position_weight=0.25; held_outside_top_n=TEST; target_weight_delta=0.03; future_reason";
    expect(humanizeBotText(text, "zh")).toBe("单一标的最高权重=0.25; 前 N 名之外的持仓=TEST; target_weight_delta=0.03; future_reason");
    expect(humanizeBotText("", "en")).toBe("");
  });

  it.each([
    ["completed", "orders_settled", "已成交", "Filled"],
    ["completed", "targets_unchanged", "目标未变", "Targets unchanged"],
    ["completed", "execution_partial", "部分成交", "Partially filled"],
    ["partial", "orders_settled", "部分成交", "Partially filled"],
    ["no_trade", "keep_cash", "本轮不交易", "No trade"],
    ["failed", "execution_partial", "运行失败", "Failed"],
  ] as const)("labels %s / %s by outcome without overriding failures", (status, reason, zh, en) => {
    const value = { ...run, status, result: { outcome_reason: reason } };
    expect(botOutcomeLabel("zh", value)).toBe(zh);
    expect(botOutcomeLabel("en", value)).toBe(en);
  });

  it("falls back for unknown outcomes and preserves active statuses", () => {
    for (const status of ["completed", "queued", "running", "stopped", "skipped"] as const) {
      expect(botOutcomeLabel("zh", { ...run, status, result: { outcome_reason: "future_reason" } })).toBe(botRunLabel("zh", status));
    }
    expect(botOutcomeLabel("zh", { ...run, result: null })).toBe("本轮结束");
  });

  it.each([
    ["Asia/Shanghai", "北京时间", "Beijing", "23:05"],
    ["America/New_York", "纽约", "New York", "10:05"],
    ["UTC", "UTC", "UTC", "15:05"],
    ["Europe/Paris", "Europe/Paris", "Europe/Paris", "16:05"],
  ])("formats explicit %s timestamps and zone labels without CST", (zone, zh, en, time) => {
    expect(botZoneLabel(zone, "zh")).toBe(zh);
    expect(botZoneLabel(zone, "en")).toBe(en);
    expect(botTime(run.created_at, "zh", zone)).toContain(time);
    const html = renderToStaticMarkup(<PaperBotActions run={run} timeZone={zone} />);
    expect(html).toContain(`${time} ${zh}`);
    expect(html).not.toContain(" CST");
  });

  it("handles DST and missing timestamp values", () => {
    expect(botZonedTime("2026-07-06T15:05:00Z", "en", "America/New_York")).toContain("11:05 New York");
    expect(botZonedTime(null, "zh", "Asia/Shanghai")).toBe("—");
    expect(botZonedTime("bad-date", "en", "UTC")).toBe("—");
  });

  it("renders four sections, existing evidence, humanized reasoning and collapsed original", () => {
    const value = { ...run, result: { ...run.result, context: { research_run_id: 78, research_as_of: "2026-11-05", evidence_ids: ["rating:1", "position:TEST"] } } };
    const html = renderToStaticMarkup(<PaperBotDecisionSummary run={value} timeZone="America/New_York" />);
    for (const title of ["结论", "动作", "理由", "证据"]) expect(html).toContain(`>${title}</h3>`);
    const [summary, original] = html.split("<details");
    expect(summary).toContain("已成交");
    expect(summary).toContain("订单处理阶段结束");
    expect(summary).toContain("保留现有持仓；目标权重=0.2；研究批次=78。");
    expect(summary).toContain("rating:1, position:TEST");
    expect(summary).toContain("2026-11-05");
    expect(summary).toContain("10:05 纽约");
    expect(summary).not.toContain(" CST");
    expect(original).toContain(">原文</summary>");
    expect(original).toContain(run.summary);
    expect(original).not.toMatch(/\bopen(?:=|\s|>)/);
  });

  it("leaves missing evidence unknown and renders planned targets without inventing fills", () => {
    const value = { ...run, result: { decision: { actions: [{ action_id: "plan1", ticker: "PLAN", target_weight: 0.25 }] }, actions: [] } };
    const html = renderToStaticMarkup(<PaperBotDecisionSummary run={value} timeZone="UTC" />);
    expect(html).toContain("PLAN");
    expect(html).toContain("25.0%");
    expect(html).toContain("执行状态待确认");
    expect(html).toContain("证据编号</dt><dd class=\"break-words font-tm-mono\">—</dd>");
    expect(html).not.toContain("10:05");
    expect(html).not.toContain("订单现状");
  });

  it("labels per-run counts and cumulative account fees separately", () => {
    const execution = renderToStaticMarkup(<PaperBotExecutionSummary run={run} />);
    expect(execution).toContain("实际订单 · 本轮 · 1");
    expect(execution).toContain("$0.05");
    const html = renderToStaticMarkup(<PaperBotPerformanceSummary data={performance} />);
    expect(html).toContain("$1.25");
    expect(html).toContain("账户累计");
  });

  it("shows matched sample length with warning below 252, retaining a real zero", () => {
    const sample = botSampleLength(performance, "zh");
    expect(sample.count).toBe(19);
    expect(sample.label).toBe("样本 19 个交易日 · 协议要求 252 个可比交易日");
    expect(sample.tone).toBe("text-tm-warn");
    const html = renderToStaticMarkup(<PaperBotPerformanceSummary data={performance} />);
    expect(html).toContain(`class="text-xs leading-5 text-tm-warn">${sample.label}</p>`);
    const zero = botSampleLength({ ...performance, matched_window: { sample_count: 0 } }, "zh");
    expect(zero.count).toBe(0);
    expect(zero.tone).toBe("text-tm-warn");
  });

  it("falls back only when matched sample count is absent and clears the warning at 252", () => {
    expect(botSampleLength({ history: { valid_nav_count: 20 }, matched_window: {} }, "zh").count).toBe(20);
    expect(botSampleLength({ history: { valid_nav_count: 20 }, matched_window: { sample_count: null } }, "zh").count).toBe(20);
    const sample = botSampleLength({ ...performance, matched_window: { sample_count: 252 } }, "en");
    expect(sample.tone).toBe("text-tm-muted");
    expect(sample.label).toBe("Sample: 252 trading days · Protocol requires 252 comparable trading days");
  });

  it("shows the unavailable no-model control in the summary without estimates", () => {
    const html = renderToStaticMarkup(<PaperBotPerformanceSummary data={performance} />);
    expect(html).toContain(">无模型对照：暂无同条件账本</p>");
    expect(html).not.toContain("NaN");
  });
});
