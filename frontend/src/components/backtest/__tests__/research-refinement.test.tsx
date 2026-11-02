import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { BacktestFormSticky } from "../BacktestFormSticky";
import { BacktestEmptyState } from "../BacktestEmptyState";
import { RecentRunsTable } from "../RecentRunsTable";
import { DEFAULT_PARAMS } from "../useBacktestSession";
import type { Run } from "../types";

const noop = () => {};
describe("Backtest research refinement", () => {
  it("keeps cost visible but removes collapsed advanced controls from keyboard order", () => {
    const html = renderToStaticMarkup(<BacktestFormSticky params={DEFAULT_PARAMS} setParams={noop} isRunning={false} onRun={noop} />);
    expect(html).toContain("因子表达式");
    expect(html).toContain("成本与验证设置");
    expect(html).toContain("bps");
    expect(html).not.toContain('id="backtest-include-breakdown"');
    expect(html).toContain("多空组合");
  });
  it("freezes form while computing", () => {
    const html = renderToStaticMarkup(<BacktestFormSticky params={DEFAULT_PARAMS} setParams={noop} isRunning onRun={noop} />);
    expect(html).toMatch(/<fieldset[^>]*disabled/);
  });
  it("shows the same five validation questions without passing unknown checks", () => {
    const html = renderToStaticMarkup(<BacktestEmptyState running={false} />);
    expect(html).toContain("尚未评估");
    for (const label of ["样本外表现", "Walk-forward 稳定性", "交易成本韧性", "持仓集中度", "前视与数据风险"]) expect(html).toContain(label);
    expect(html).not.toContain("animate-pulse");
  });
  it("bounds recent history to five rows without dropping later runs", () => {
    const runs = Array.from({length: 7}, (_, i) => ({id: String(i), ts: i, params: DEFAULT_PARAMS, metrics: {sharpe:null,maxDD:null,ic:null,turnover:null,annReturn:null}} as Run));
    const html = renderToStaticMarkup(<RecentRunsTable runs={runs} baselineRunId={null} onRefill={noop} onTogglePin={noop} onSaveToZoo={noop} />);
    expect(html).toContain("7 次运行");
    expect(html).toContain("1 / 2");
    expect((html.match(/<tr\b/g) ?? []).length).toBe(6);
  });
});
