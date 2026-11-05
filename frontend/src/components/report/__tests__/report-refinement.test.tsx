import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ReportComposer, ReportEvidenceEmpty, filterReportLibrary, reportDirectionLabel, isReportDraftDirty, type ReportConfig } from "../ReportComposer";
import { ReportDeepModal } from "../ReportDeepModal";
import { ReportVerdictHero } from "../ReportVerdictHero";
import { FACTOR_EXAMPLES } from "@/components/alpha/FactorExamples";
import type { FactorBacktestResponse } from "@/lib/types";

const noop = () => {};
const config: ReportConfig = { direction: "long_short", neutralize: "none", benchmarkTicker: "SPY", transactionCostBps: 5 };
const props = { factorName: "", onFactorName: noop, expr: "", onExpr: noop, config, onConfig: noop, zoo: [], running: false, sourceName: null, onExample: noop, onZoo: noop, onGenerate: noop };

describe("Report in-place refinement", () => {
  it("blocks invalid report costs without changing saved settings", () => {
    const html = renderToStaticMarkup(<ReportComposer {...props} expr="rank(close)" config={{ ...config, transactionCostBps: -1 }} />);
    expect(html).toContain("请输入 0 至 200 的数值");
    expect(html).toContain('aria-invalid="true"');
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*bg-tm-accent/);
  });
  it("marks any unrun input change without invalidating the previous report snapshot", () => {
    const report = { name: "factor", expression: "rank(close)", config: { ...config } };
    expect(isReportDraftDirty("factor", " rank(close) ", config, report)).toBe(false);
    expect(isReportDraftDirty("renamed", "rank(close)", config, report)).toBe(true);
    expect(isReportDraftDirty("factor", "rank(volume)", config, report)).toBe(true);
    expect(isReportDraftDirty("factor", "rank(close)", { ...config, transactionCostBps: 10 }, report)).toBe(true);
    expect(isReportDraftDirty("factor", "rank(close)", { ...config, direction: "long_only" }, report)).toBe(true);
    expect(isReportDraftDirty("factor", "rank(close)", { ...config, neutralize: "sector" }, report)).toBe(true);
    expect(isReportDraftDirty("factor", "rank(close)", { ...config, benchmarkTicker: "RSP" }, report)).toBe(true);
    expect(isReportDraftDirty("", "rank(close)", config, { ...report, name: "user_factor" })).toBe(false);
    expect(report.config.transactionCostBps).toBe(5);
  });
  it("starts with the composer and one explicit generation action, not fixture results", () => {
    const html = renderToStaticMarkup(<ReportComposer {...props} />);
    expect(html).toContain("生成报告");
    expect(html).toContain("从示例 / 因子库载入");
    expect(html).toContain("多空");
    expect(html).toContain("不中性化");
    expect(html).not.toContain("Earnings Yield");
    expect(html).not.toContain("testSharpe");
    expect(html).not.toContain("long_short");
    expect(html).not.toContain('role="dialog"');
    expect(html.match(/<button[^>]*bg-tm-accent\b/g)).toHaveLength(1);
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*bg-tm-accent/);
  });

  it("keeps inputs and source selection frozen during a run", () => {
    const html = renderToStaticMarkup(<ReportComposer {...props} expr="rank(close)" running />);
    expect(html).toMatch(/<fieldset[^>]*disabled/);
    expect(html).toMatch(/<textarea[^>]*disabled/);
    expect(html).toContain('aria-busy="true"');
    expect(html).toContain("正在生成报告");
  });

  it("searches every entry before a bounded page is selected", () => {
    const all = Array.from({ length: 13 }, (_, index) => ({ name: `Factor ${index}`, expression: `rank(field_${index})` }));
    expect(filterReportLibrary(all, "")).toHaveLength(13);
    expect(filterReportLibrary(all, " FIELD_12 ")).toEqual([all[12]]);
    expect(filterReportLibrary(all, "missing")).toHaveLength(0);
    expect(filterReportLibrary(FACTOR_EXAMPLES, "volume").length).toBeGreaterThan(0);
    expect(all.slice(10, 15)).toHaveLength(3);
    expect(reportDirectionLabel("long_only", "zh")).toBe("只做多");
    expect(reportDirectionLabel("short_only", "en")).toBe("Short only");
  });

  it("does not turn missing or pending evidence into zero returns or positive verdicts", () => {
    const idle = renderToStaticMarkup(<ReportEvidenceEmpty running={false} failed={false} hasDraft={false} />);
    expect(idle).toContain("尚无本次结果");
    expect(idle).not.toContain("0.00");
    expect(idle).not.toContain("animate");
    const failed = renderToStaticMarkup(<ReportEvidenceEmpty running={false} failed hasDraft />);
    expect(failed).toContain("草稿与参数仍保留");
    const pending = renderToStaticMarkup(<ReportEvidenceEmpty running failed={false} hasDraft />);
    expect(pending).toContain("正在汇总研究证据");
    expect(pending).toContain('aria-busy="true"');
  });

  it("derives a cautious verdict from current evidence and has no second source chooser", () => {
    const backtest = { alpha_pvalue: 0.22, beta_market: 0.1, test_metrics: { sharpe: 1.52 }, overfit_flag: false } as FactorBacktestResponse;
    const html = renderToStaticMarkup(<ReportVerdictHero primary={{ name: "factor", expression: "rank(close)", backtest }} running={false} />);
    expect(html).toContain("未见显著 Alpha");
    expect(html).not.toContain("低市场暴露 Alpha");
    expect(html).not.toContain("button");
    const missing = renderToStaticMarkup(<ReportVerdictHero primary={{ name: "factor", expression: "rank(close)", backtest: { ...backtest, alpha_pvalue: undefined } }} running={false} />);
    expect(missing).toContain("证据不足");
  });

  it("retains deep evidence for printing without opening a floating action or dialog", () => {
    const html = renderToStaticMarkup(<ReportDeepModal open={false} onOpen={noop} onClose={noop}><p>Diagnostic evidence</p></ReportDeepModal>);
    expect(html).toContain('class="hidden print:block"');
    expect(html).toContain("Diagnostic evidence");
    expect(html).not.toContain("fixed bottom");
    expect(html).not.toContain('role="dialog"');
  });
});
