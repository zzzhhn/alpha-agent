import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import type { FundamentalsData, RatingCard } from "@/lib/api/picks";
import FundamentalsBlock, { withinBounds } from "../FundamentalsBlock";
import CatalystsBlock from "../CatalystsBlock";
import MarketContextWidget, { MarketContextContent } from "../MarketContextWidget";

const language = vi.hoisted(() => ({ locale: "zh" as "zh" | "en" }));
vi.mock("@/components/layout/LocaleProvider", () => ({ useLocale: () => language }));

const card: RatingCard = {
  ticker: "NVDA", rating: "BUY", confidence: 0.8, composite_score: 1,
  as_of: "2026-11-11T00:00:00Z", breakdown: [], top_drivers: [], top_drags: [],
};
const fundamentals: FundamentalsData = {
  pe_trailing: 30, pe_forward: 25, eps_ttm: 5, market_cap: 3e12,
  dividend_yield: 0.1, profit_margin: 0.637, debt_to_equity: 20, beta: 1.5,
};
function withFundamentals(values: Partial<FundamentalsData> = {}): RatingCard {
  return { ...card, breakdown: [{ signal: "factor", z: 1, weight: 1, weight_effective: 1,
    contribution: 1, source: "test", timestamp: card.as_of, error: null,
    raw: { fundamentals: { ...fundamentals, ...values } } }] };
}
beforeEach(() => { language.locale = "zh"; });

describe("fundamentals bounds in raw units", () => {
  it.each([-5, -1.5, 0, 0.637, 1, null])("accepts margin %s", (value) => {
    expect(withinBounds("profit_margin", value)).toBe(true);
  });
  it.each([-5.001, 1.001, NaN, Infinity, -Infinity])("rejects margin %s", (value) => {
    expect(withinBounds("profit_margin", value)).toBe(false);
  });
  it.each([
    ["pe_trailing", 0.5, 500], ["pe_forward", 0.5, 500], ["eps_ttm", -50, 500],
    ["dividend_yield", 0, 25], ["debt_to_equity", 0, 2000], ["beta", -3, 5],
  ] as const)("preserves %s bounds", (field, low, high) => {
    expect(withinBounds(field, low)).toBe(true);
    expect(withinBounds(field, high)).toBe(true);
    expect(withinBounds(field, low - 0.01)).toBe(false);
    expect(withinBounds(field, high + 0.01)).toBe(false);
    expect(withinBounds(field, null)).toBe(true);
  });
  it("does not introduce a market-cap bound", () => {
    expect(withinBounds("market_cap", 5e12)).toBe(true);
  });
  it("renders NVDA's 63.7% margin and keeps dividend percent units unchanged", () => {
    const html = renderToStaticMarkup(<FundamentalsBlock card={withFundamentals()} />);
    expect(html).toContain("63.70%");
    expect(html).toContain("0.10%");
    expect(html).not.toContain("已隐藏");
  });
  it("renders a visible Chinese reason with the raw value underneath a rejected cell", () => {
    const html = renderToStaticMarkup(<FundamentalsBlock card={withFundamentals({ profit_margin: 1.2 })} />);
    expect(html).toContain('<p class="text-xs leading-relaxed text-tm-warn">超出合理范围（原值 1.2），已隐藏</p>');
    expect(html).not.toContain("120.00%");
  });
  it("renders the English anomaly reason and keeps missing cells distinct", () => {
    language.locale = "en";
    const html = renderToStaticMarkup(<FundamentalsBlock card={withFundamentals({ pe_forward: -3, profit_margin: null })} />);
    expect(html).toContain("Outside the reasonable range (raw value -3); hidden");
    expect(html.match(/Outside the reasonable range/g)).toHaveLength(1);
  });
});

describe("compact reference states", () => {
  it("renders each empty catalyst as one paragraph with its label on the same line", () => {
    const html = renderToStaticMarkup(<CatalystsBlock card={card} />);
    const lines = html.match(/<p\b[^>]*>[\s\S]*?<\/p>/g) ?? [];
    expect(lines).toHaveLength(2);
    expect(lines[0]).toContain("下次财报</span>无已知财报日期");
    expect(lines[1]).toContain("宏观日历</span>近期无相关宏观事件");
    expect(html).not.toContain("grid-cols-3");
    expect(html).not.toContain("mb-2");
  });
  it("preserves populated earnings and calendar data", () => {
    const populated: RatingCard = { ...card, breakdown: [
      { signal: "earnings", z: 0, weight: 0, weight_effective: 0, contribution: 0,
        source: "test", timestamp: card.as_of, error: null,
        raw: { next_date: "2026-11-19", days_until: 8, eps_estimate: 1.25, revenue_estimate: 50e9 } },
      { signal: "calendar", z: 0, weight: 0, weight_effective: 0, contribution: 0,
        source: "test", timestamp: card.as_of, error: null, raw: ["CPI release"] },
    ] };
    const html = renderToStaticMarkup(<CatalystsBlock card={populated} />);
    expect(html).toContain("2026-11-19");
    expect(html).toContain("1.25");
    expect(html).toContain("$50.00B");
    expect(html).toContain("CPI release");
    expect(html).not.toContain("无已知财报日期");
  });
  it("starts the widget with an explicit loading line", () => {
    const html = renderToStaticMarkup(<MarketContextWidget ticker="NVDA" />);
    expect(html).toContain("正在加载宏观事件…");
    expect(html).toContain('aria-busy="true"');
    expect(html).not.toContain(">...</");
  });
  it.each(["zh", "en"] as const)("distinguishes loading, error and empty in %s", (locale) => {
    const loading = renderToStaticMarkup(<MarketContextContent state={{ status: "loading" }} locale={locale} />);
    const error = renderToStaticMarkup(<MarketContextContent state={{ status: "error" }} locale={locale} />);
    const empty = renderToStaticMarkup(<MarketContextContent state={{ status: "ready", items: [] }} locale={locale} />);
    expect(loading).toContain(locale === "zh" ? "正在加载宏观事件…" : "Loading macro events…");
    expect(error).toContain(locale === "zh" ? "宏观事件暂时无法加载，请稍后重试。" : "Macro events could not be loaded. Please try again later.");
    expect(error).toContain("text-tm-warn");
    expect(empty).toContain(locale === "zh" ? "近 7 天无该 ticker 相关的宏观事件" : "No relevant market-wide events in the last 7 days");
    for (const html of [loading, error, empty]) {
      expect(html.match(/<p\b/g)).toHaveLength(1);
      expect(html).toContain("items-baseline");
      expect(html).not.toContain("mb-2");
    }
  });
  it("keeps populated macro context linked with its evidence", () => {
    const html = renderToStaticMarkup(<MarketContextContent locale="en" state={{ status: "ready", items: [{
      id: 1, author: "fed", title: "Rate decision", url: "https://example.com/event",
      body_excerpt: "Policy update", published_at: new Date().toISOString(), sentiment_score: -0.5,
      tickers_extracted: ["NVDA"], sectors_extracted: ["Technology"],
    }] }} />);
    expect(html).toContain('href="https://example.com/event"');
    expect(html).toContain("Policy update");
    expect(html).toContain("Technology");
    expect(html).toContain("bg-tm-neg");
  });
});
