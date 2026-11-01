import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import InvestmentProfile from "../InvestmentProfile";
import InvestmentNotebook from "../InvestmentNotebook";
import InvestmentEvidence from "../InvestmentEvidence";

describe("optional compact panels on Picks", () => {
  it("keeps the plan entry while deferring its explanation; default consumers stay unchanged", () => {
    const compact = renderToStaticMarkup(<InvestmentProfile compact />);
    expect(compact).toContain("我的投资计划");
    expect(compact).toContain('aria-expanded="false"');
    expect(compact).not.toContain("先明确期限与现有持仓");
    expect(renderToStaticMarkup(<InvestmentProfile />)).toContain("先明确期限与现有持仓");
  });

  it("keeps the notebook accessible without rendering a closed form", () => {
    const compact = renderToStaticMarkup(<InvestmentNotebook compact />);
    expect(compact).toContain("打开或收起研究记录");
    expect(compact).not.toContain("为什么关注");
    expect(compact).not.toContain("textarea");
    expect(renderToStaticMarkup(<InvestmentNotebook />)).toContain("为什么关注");
  });

  it("shows truthful loading in the evidence summary without mounting hidden charts", () => {
    const compact = renderToStaticMarkup(<InvestmentEvidence sleeve="tactical" compact />);
    expect(compact).toContain("正在读取策略账本");
    expect(compact).toContain('aria-controls="picks-evidence-details"');
    expect(compact).not.toContain("0.00%");
    expect(compact).not.toContain("同区间策略净收益");
    expect(renderToStaticMarkup(<InvestmentEvidence sleeve="tactical" />)).toContain("跟随这套策略，结果怎样");
  });
});
