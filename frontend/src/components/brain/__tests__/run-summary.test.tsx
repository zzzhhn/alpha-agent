import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { BrainDiagnostic, BrainMiningPanel, BrainRunSummaryStrip } from "../BrainMiningPanel";
import { BrainCandidateAudit, BrainStatusLegend } from "../BrainCandidateAudit";
import { fetchBrainRunsSummary, type BrainRunsSummary } from "@/lib/api/brain";
import { apiGet } from "@/lib/api/client";

vi.mock("@/lib/api/client", () => ({ apiGet: vi.fn(), apiPost: vi.fn() }));

const summary: BrainRunsSummary = {
  total_runs: 168,
  by_status: { queued: 1, running: 2, completed: 160, failed: 5 },
  totals: { generated: 1000, simulated: 500, passed: 40, flagged: 60, rejected: 380, sim_error: 20 },
  last_30d: [{ date: "2026-11-11", runs: 12, passed: 3, flagged: 4, rejected: 5, sim_error: 0 }],
  first_run_at: null, last_run_at: null,
};

function strip(data: BrainRunsSummary | null, loading = false, error = false) {
  return renderToStaticMarkup(<BrainRunSummaryStrip summary={data} loading={loading} error={error} zh />);
}

describe("BRAIN summary and review clarity", () => {
  it("requests the static summary endpoint with caller options", () => {
    const options = { timeoutMs: 5000 };
    fetchBrainRunsSummary(options);
    expect(apiGet).toHaveBeenCalledWith("/api/brain/runs/summary", options);
  });

  it("renders cross-run totals and the separate UTC 30-day count", () => {
    const html = strip(summary);
    for (const value of ["总运行", "168", "已完成", "160", "失败", "存疑", "淘汰", "仿真错误", "近 30 天（UTC）", "12"]) {
      expect(html).toContain(value);
    }
    expect(html).not.toContain("汇总读取失败");
  });

  it("does not disguise loading or errors as zero or stale totals", () => {
    const loading = strip(summary, true);
    expect(loading).toContain("正在读取跨运行汇总");
    expect(loading).toContain('aria-busy="true"');
    const failed = strip(summary, false, true);
    expect(failed).toContain("汇总读取失败");
    for (const html of [loading, failed]) {
      expect(html).toContain("—");
      expect(html).not.toContain(">168<");
      expect(html).not.toContain(">0<");
      expect(html).not.toContain("暂无挖矿运行");
    }
  });

  it("distinguishes no runs ever from no runs in the last 30 days", () => {
    expect(strip({ ...summary, total_runs: 0, last_30d: [] })).toContain("暂无挖矿运行");
    const older = strip({ ...summary, last_30d: [] });
    expect(older).toContain("期间无运行");
    expect(older).not.toContain("暂无挖矿运行");
  });

  it("shows the translation before an initially collapsed raw log", () => {
    const raw = "BRAIN authentication failed: HTTP 401";
    const html = renderToStaticMarkup(<BrainDiagnostic line={raw} zh />);
    expect(html.indexOf("身份验证失败")).toBeLessThan(html.indexOf("<details"));
    expect(html).toContain("原始日志");
    expect(html).toContain(raw);
    expect(html).not.toMatch(/<details[^>]*\bopen/);
  });

  it("keeps outcome, screen and candidate meanings available in the audit legend", () => {
    const legend = renderToStaticMarkup(<BrainStatusLegend zh />);
    for (const label of ["passed", "flagged", "rejected", "sim_error", "pending", "completed", "partial", "timeout", "error", "fallback", "fallback_partial", "bypassed", "failed", "legacy", "selected", "withheld", "不代表未来收益"]) {
      expect(legend).toContain(label);
    }
    expect(legend).not.toMatch(/<details[^>]*\bopen/);
    expect(renderToStaticMarkup(<BrainCandidateAudit runId={1} />)).toContain("状态图例");
  });

  it("places quota and GitHub Actions costs beside the mining form without confirmation", () => {
    const html = renderToStaticMarkup(<BrainMiningPanel />);
    expect(html).toContain("开始挖矿");
    expect(html).toContain("本次请求 12 次仿真预算");
    expect(html).toContain("你的 BRAIN 账户仿真配额");
    expect(html).toContain("GitHub Actions");
    expect(html).toContain("金额成本未知，此处不追踪");
    expect(html).not.toContain('role="dialog"');
  });
});
