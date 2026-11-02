import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import type { OrderOut } from "@/lib/api/paper";
import PaperPositionsWithSource from "../PaperPositionsWithSource";
import PaperSourceSummary from "../PaperSourceSummary";
import PaperOrdersPane from "../PaperOrdersPane";
import PaperCurvePane from "../PaperCurvePane";
import SimOrderForm from "../../SimOrderForm";

describe("paper workspace refinement", () => {
  it("keeps confirmed positions visible when attribution is unavailable", () => {
    const html = renderToStaticMarkup(<PaperPositionsWithSource positions={[{ticker:"AAPL",qty:10,avg_cost:100,current_price:110,unrealized_pnl:100,unrealized_pct:10}]} attribution={[]} attributionAvailable={false} />);
    expect(html).toContain("AAPL");
    expect(html).toContain("来源待确认");
    expect(html).not.toContain("自主交易");
  });
  it("distinguishes pending execution from a filled position", () => {
    const html = renderToStaticMarkup(<PaperPositionsWithSource positions={[]} attribution={[]} pendingOrders={2} onChoose={() => {}} />);
    expect(html).toContain("2 笔订单待成交");
    expect(html).toContain("查看下单区");
    expect(html).not.toContain("下单”标签");
  });
  it("does not report unrecorded sources or equity as zero returns", () => {
    const sources = renderToStaticMarkup(<PaperSourceSummary rows={[]} />);
    expect(sources).not.toContain("+$0");
    const curve = renderToStaticMarkup(<PaperCurvePane curve={{series:[],base_date:null}} compact showDisclaimer={false} />);
    expect(curve).toContain("等待首个净值记录");
    expect(curve).toContain("没有数据不代表零收益");
  });
  it("bounds loaded order history while preserving its total", () => {
    const orders:OrderOut[] = Array.from({length:12},(_,i)=>({id:i+1,ticker:`TEST${i+1}`,side:"buy",order_type:"market",qty:1,limit_price:null,signal_date:"2026-10-30",fill_date:null,fill_price:null,status:"pending"}));
    const html = renderToStaticMarkup(<PaperOrdersPane orders={orders} onCancel={async()=>{}} attribution={[]} attributionStatus="ready" showAttribution={false} />);
    const body = html.match(/<tbody[^>]*>([\s\S]*?)<\/tbody>/)?.[1] ?? "";
    expect(body.match(/<tr\b/g)).toHaveLength(5);
    expect(html).toContain("本次已载入 12 笔订单");
  });
  it("disables submission while account context is refreshing", () => {
    const html = renderToStaticMarkup(<SimOrderForm fixedTicker="TEST" locale="zh" layout="ticket" disabled availableCash={1000} onPlaced={() => {}} />);
    expect(html).toMatch(/<button[^>]*type="submit"[^>]*disabled/);
  });

  it("keeps missing bot PnL unknown and identifies account-level provenance", () => {
    const html = renderToStaticMarkup(<PaperPositionsWithSource accountKind="bot" positions={[{ticker:"TEST",qty:10,avg_cost:100,current_price:110,unrealized_pnl:null,unrealized_pct:null}]} attribution={[]} attributionAvailable={false} />);
    expect(html).toContain("机器人账户");
    expect(html).not.toContain("自主交易");
    expect(html).not.toContain("+$0");
  });

  it("does not expose manual cancellation controls on bot orders", () => {
    const order:OrderOut = {id:1,ticker:"TEST",side:"buy",order_type:"market",qty:1,limit_price:null,signal_date:"2026-10-30",fill_date:null,fill_price:null,status:"pending"};
    const html = renderToStaticMarkup(<PaperOrdersPane botMode orders={[order]} onCancel={async()=>{}} attribution={[]} attributionStatus="unavailable" showAttribution={false} showDisclaimer={false} />);
    expect(html).not.toMatch(/<button\b/);
    expect(html).toContain("待成交");
  });
});
