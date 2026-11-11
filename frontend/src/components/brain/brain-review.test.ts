import { describe, expect, it } from "vitest";
import { DEFAULT_BRAIN_PAGE_SIZE, brainSubmissionState, familyLabel, hasUnsimulatedCandidates, nextExpandedAlpha, runFailureAction, translateBrainDiagnostic } from "./brain-review";

describe("BRAIN diagnostic translation", () => {
  it.each([
    ["BrainAuthError: BRAIN authentication failed: HTTP 401", "身份验证失败"],
    ["no BRAIN credentials configured", "尚未配置"],
    ["credential load failed: CryptoError", "凭据读取失败"],
    ["simulate rejected: HTTP 429: Too many requests", "限流"],
    ["simulation abc timed out after 600.0s (last status PENDING)", "仿真等待超时"],
    ["simulation abc failed: unknown variable 'foo'", "无法识别"],
    ["below in-sample gates (BRAIN submission bars)", "样本内绩效门槛"],
    ["LOW_FITNESS: FAIL", "Fitness 未达到"],
    ["LOW_SHARPE: FAIL", "Sharpe 未达到"],
    ["HIGH_TURNOVER: FAIL", "换手率不符合"],
    ["SELF_CORRELATION: FAIL", "自相关未通过"],
    ["self-correlation near official limit: 0.6800 (warning 0.65, hard 0.70)", "自相关接近"],
    ["high-quality-but-redundant; mechanism=value; self-corr official=0.8", "边际贡献不足"],
    ["family 'value' saturated (2 rep(s))", "代表名额已满"],
    ["ConnectError: connection refused", "网络连接失败"],
    ["ReadTimeout", "网络请求超时"],
    ["GH_PAT not configured; cannot dispatch mining", "未配置 GitHub"],
    ["GitHub API 422: failure", "GitHub 派发失败（HTTP 422）"],
    ["dispatch failed: RemoteProtocolError", "任务派发失败"],
    ["no logic-screen LLM configured", "使用规则筛选"],
    ["full-pool logic screen timed out after 240s; scored 0/24 expressions", "逻辑预筛超时"],
    ["full-pool logic screen failed (NoUsableScores)", "逻辑预筛不可用"],
    ["candidate generation produced no usable expressions for family=options; no BRAIN simulations were submitted", "未生成可用表达式"],
    ["simulate returned no Location/sim_id", "缺少仿真或因子标识"],
    ["simulation abc failed: SIMULATION_ERROR", "未能完成"],
  ])("translates known diagnostic %s and preserves English locale", (raw, translated) => {
    expect(translateBrainDiagnostic(raw, "zh")).toContain(translated);
    expect(translateBrainDiagnostic(raw, "en")).toBe(raw);
  });

  it("preserves unknown content, successful metrics and separators", () => {
    for (const line of ["future diagnostic: x", "Sharpe above cutoff", "", "中文诊断"]) {
      expect(translateBrainDiagnostic(line, "zh")).toBe(line);
    }
    expect(translateBrainDiagnostic("scored 3/24 expressions in one full-pool call; partial scores retained\nfuture diagnostic: x", "zh"))
      .toBe("逻辑预筛已评分 3/24 条表达式。; 已保留返回的部分评分。\nfuture diagnostic: x");
    expect(translateBrainDiagnostic("deterministic evidence screen selected 8/24; withheld 16", "zh"))
      .toBe("规则证据筛选入选 8/24 条。; 未入选 16 条。");
  });
});

describe("BRAIN run review", () => {
  it("distinguishes rejected submissions from acceptance in both receipts and persisted rows", () => {
    const submitted_at = "2026-11-03T00:00:00Z";
    expect(brainSubmissionState({ ok: false })).toBe("rejected");
    expect(brainSubmissionState({ ok: true })).toBe("accepted");
    expect(brainSubmissionState({ submitted_at, brain_status: "submit_rejected" })).toBe("rejected");
    expect(brainSubmissionState({ submitted_at, brain_status: "submitted" })).toBe("accepted");
    expect(brainSubmissionState({ submitted_at, brain_status: null })).toBe("attempted");
  });
  it("uses ten rows by default and opens only one result at a time", () => {
    expect(DEFAULT_BRAIN_PAGE_SIZE).toBe(10);
    expect(nextExpandedAlpha(null, 160)).toBe(160);
    expect(nextExpandedAlpha(160, 161)).toBe(161);
    expect(nextExpandedAlpha(161, 161)).toBeNull();
  });

  it("opens candidate audit for generated candidates with zero simulations", () => {
    expect(hasUnsimulatedCandidates({ id: 160, generated_n: 16, simulated_n: 0 })).toBe(true);
    expect(hasUnsimulatedCandidates({ id: 160, generated_n: 16, simulated_n: 8 })).toBe(false);
    expect(hasUnsimulatedCandidates({ id: 160, generated_n: 0, simulated_n: 0 })).toBe(false);
    expect(hasUnsimulatedCandidates({ id: 160, generated_n: 16, simulated_n: null })).toBe(false);
    expect(hasUnsimulatedCandidates(null)).toBe(false);
  });

  it("localizes known families without inventing labels for new IDs", () => {
    expect(familyLabel("iv_term", true)).toBe("隐波期限结构");
    expect(familyLabel("iv_term", false)).toBe("IV term");
    expect(familyLabel(null, true)).toBe("混合家族");
    expect(familyLabel("future_family", true)).toBe("future_family");
  });

  it("summarizes dispatch failures without showing raw diagnostics", () => {
    expect(runFailureAction({ id: 160, error_detail: "GitHub API 422: raw response" }, false))
      .toContain("could not be dispatched");
    expect(runFailureAction({ id: 160, error_detail: "GitHub API 422: raw response" }, false))
      .not.toContain("raw response");
    expect(runFailureAction({ id: 160 }, false)).not.toContain("No candidates were generated");
  });
});
