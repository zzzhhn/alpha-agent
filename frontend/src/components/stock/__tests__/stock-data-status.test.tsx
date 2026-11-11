import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { stockDataStatus } from "../StockCardLayout";
import { WorkbenchHeader } from "@/components/workbench/WorkbenchHeader";

describe("stock header data status", () => {
  it.each(["zh", "en"] as const)("warns for daily-only cards in %s", (locale) => {
    const status = stockDataStatus(true, false, locale);
    expect(status.value).toBe(locale === "zh" ? "部分（仅日线）" : "Partial (daily only)");
    expect(status.tone).toBe("warning");
    const html = renderToStaticMarkup(<WorkbenchHeader title="NVDA" subtitle="" statuses={[status]} />);
    expect(html).toContain(status.value);
    expect(html).toContain("text-tm-warn");
    expect(html).not.toContain(locale === "zh" ? "最新" : "CURRENT");
  });
  it.each([false, true])("keeps stale ahead of partial=%s", (partial) => {
    expect(stockDataStatus(partial, true, "zh")).toEqual({ label: "数据状态", value: "需刷新", tone: "warning" });
    expect(stockDataStatus(partial, true, "en").value).toBe("STALE");
  });
  it("keeps a complete fresh card positive", () => {
    expect(stockDataStatus(false, false, "zh")).toEqual({ label: "数据状态", value: "最新", tone: "positive" });
    expect(stockDataStatus(false, false, "en").value).toBe("CURRENT");
  });
});
