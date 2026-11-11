import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import type { BriefingItem } from "@/lib/api/factor-lab";
import { BriefingPane } from "../BriefingPane";

function item(id: number, expression = `expression_${id}`): BriefingItem {
  return { id, expression, source: null, deflated_sharpe: null, ic_oos: null, self_correlation: 0, risk_level: null, concerns: [] };
}

describe("BriefingPane", () => {
  it("renders ten unique items total, deduped counts and TM pagination", () => {
    const html = renderToStaticMarkup(<BriefingPane locale="zh" briefing={{
      validated: Array.from({ length: 15 }, (_, index) => item(index + 1)),
      flagged: [item(20, "expression_15")], failure_insights: [],
    }} />);
    expect(html.match(/<code /g)).toHaveLength(10);
    expect(html.match(/>expression_15</g)).toHaveLength(1);
    expect(html).not.toContain(">expression_1<");
    expect(html).toContain("14 通过 · 1 存疑");
    expect(html).toContain('aria-label="挖掘简报分页"');
    expect(html).toContain("1 / 2");
    expect(html).toContain("去重后 15 条");
  });
  it("renders the empty state without pagination", () => {
    const html = renderToStaticMarkup(<BriefingPane locale="en" briefing={{ validated: [], flagged: [], failure_insights: [] }} />);
    expect(html).toContain("No briefing yet.");
    expect(html).not.toContain("<nav");
  });
});
