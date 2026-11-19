import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import type { L2Summary } from "@/lib/api/paper";
import PaperL2Evidence from "../PaperL2Evidence";

it("labels missing benchmark evidence and distinguishes it from a real zero return", () => {
  const summary: L2Summary = {
    status: "ready",
    periods: 3,
    net_return: 0.01,
    spy_return: null,
    rsp_return: null,
    benchmark_status: { SPY: "partial", RSP: "missing" },
    series: [],
    sector_exposure: [],
  };
  const incomplete = renderToStaticMarkup(<PaperL2Evidence summary={summary} />);
  expect(incomplete).toContain("SPY：部分期间缺数据");
  expect(incomplete).toContain("RSP：暂无基准数据");
  expect(incomplete).not.toContain("+0.00%");
  const complete = renderToStaticMarkup(<PaperL2Evidence summary={{
    ...summary,
    spy_return: 0,
    benchmark_status: { SPY: "complete", RSP: "missing" },
  }} />);
  expect(complete).toContain("+0.00%");
  expect(complete).not.toContain("SPY：部分期间缺数据");
});
