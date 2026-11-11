import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { HypothesisInputCard } from "../HypothesisInputCard";
import { EvidencePaneGrid } from "../EvidencePaneGrid";
import { VerdictBar } from "../VerdictBar";
import type { AlphaValidationParams } from "../useAlphaChain";

const noop = () => {};
const validation: AlphaValidationParams = {direction:"long_short",topPct:30,transactionCostBps:10,neutralize:"none",benchmarkTicker:"SPY"};
const props = {text:"",onTextChange:noop,universe:"SP500" as const,onUniverseChange:noop,validation,onValidationChange:noop,onSubmit:noop,canRerun:false,onRerun:noop,disabled:false,examples:[],onExampleSelect:noop,history:[],onHistorySelect:noop};

describe("Alpha in-place refinement", () => {
  it("localizes displayed parameters without altering request values", () => {
    const html = renderToStaticMarkup(<HypothesisInputCard {...props} />);
    expect(html).toMatch(/<option value="long_short"[^>]*selected="">多空/);
    expect(html).toMatch(/<option value="none"[^>]*selected="">不中性化/);
    expect(html).toContain('aria-expanded="false"');
    expect(html).not.toContain("按当前参数重测");
  });
  it("keeps parameter-only rerun after translation and freezes input during a run", () => {
    const html = renderToStaticMarkup(<HypothesisInputCard {...props} text="test hypothesis" canRerun disabled />);
    expect(html).toContain("按当前参数重测");
    expect(html).toMatch(/<fieldset[^>]*disabled/);
    expect(html).toMatch(/<textarea[^>]*disabled/);
    expect(html).toMatch(/<button[^>]*disabled[^>]*>[\s\S]*?按当前参数重测/);
  });
  it("keeps idle evidence truthful and does not show loading or invented results", () => {
    const html = renderToStaticMarkup(<EvidencePaneGrid state={{kind:"idle"}} panes={{spec:"waiting",smoke:"waiting",backtest:"waiting"}} onReTranslate={noop} onRetryBacktest={noop} />);
    // One combined placeholder before the first run instead of three empty panes.
    expect(html).toContain("尚未运行");
    expect(html.match(/data-state="waiting"/g) ?? []).toHaveLength(0);
    expect(html).not.toContain("animate-pulse");
    const verdict = renderToStaticMarkup(<VerdictBar state={{kind:"idle"}} metrics={{ic:null,sharpe:null,maxDrawdown:null}} thresholds={{ic:null,sharpe:null,maxDrawdown:null}} canSave={false} onSave={noop} onReTranslate={noop} />);
    expect(verdict).toContain("等待验证");
    expect(verdict).not.toContain("0.00");
  });
});
