import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import type { RatingCard } from "@/lib/api/picks";
import PicksTable from "../PicksTable";
import { PicksEvidenceDetails } from "../PicksEvidenceDialog";

const card: RatingCard = {
  ticker: "TEST", rating: "HOLD", confidence: null, agreement: null,
  composite_score: 0.2, as_of: "2026-11-01T08:25:00Z",
  breakdown: [], top_drivers: [], top_drags: [],
  consistency: { d5: 0.5, m1: null, y1: null, hist: 0.6 },
  consistency_n: { d5: 2, m1: 2, y1: 2, hist: 10 },
};

describe("candidate browsing", () => {
  it("starts with 10 of 50 candidates and preserves the complete count", () => {
    const picks = Array.from({ length: 50 }, (_, i) => ({ ...card, ticker: `STOCK${i + 1}` }));
    const html = renderToStaticMarkup(<PicksTable picks={picks} />).replace(/<!--.*?-->/g, "");
    const body = html.match(/<tbody[^>]*>([\s\S]*?)<\/tbody>/)?.[1] ?? "";
    expect(body.match(/<tr\b/g)).toHaveLength(10);
    expect(body).toContain("STOCK10");
    expect(body).not.toContain("STOCK11");
    expect(html).toContain("第 1 至 10 条，共 50 条");
    expect(html).toContain("第 1 / 5 页");
    expect(html).toContain('aria-haspopup="dialog"');
  });

  it("keeps sample minimums and missingness explicit in structured evidence", () => {
    const html = renderToStaticMarkup(<PicksEvidenceDetails card={card} locale="zh" />).replace(/<!--.*?-->/g, "");
    expect(html).toContain("2 / 3");
    expect(html).toContain("样本不足");
    expect(html).toContain("60%");
    expect(html).not.toContain("50%");
    expect(html).not.toContain(">0%</");
    expect(html).toContain("历史一致度不代表未来胜率或收益");
  });

  it("does not treat legacy unknown sample counts as reliable evidence", () => {
    const html = renderToStaticMarkup(<PicksEvidenceDetails card={{ ...card, consistency_n: null }} locale="en" />);
    expect(html).toContain("Count unknown");
    expect(html).toContain("cannot establish reliability");
    expect(html).toContain("Alternative: include HOLD");
  });
});
