import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: () => {} }) }));
vi.mock("@/components/layout/SystemHealth", () => ({ useAdminAccess: () => true }));

import { LiveExpressionPanel, PRESET_FACTOR_EXPRESSION, isPresetExpression } from "../LiveExpressionPanel";

describe("live expression preset restore", () => {
  it("recognizes the platform preset regardless of spacing", () => {
    expect(isPresetExpression(PRESET_FACTOR_EXPRESSION)).toBe(true);
    expect(isPresetExpression("subtract(rank(ts_mean(returns,12)),rank(ts_std(returns,60)))")).toBe(true);
    expect(isPresetExpression("group_neutralize(zscore(ts_zscore(volume,20)),sector)")).toBe(false);
  });

  it("offers restore only for a custom expression and labels its data source", () => {
    const custom = renderToStaticMarkup(<LiveExpressionPanel locale="zh" expression="group_neutralize(zscore(ts_zscore(volume,20)),sector)" />);
    expect(custom).toContain("恢复预设");
    expect(custom).toContain("自定义表达式");
    const preset = renderToStaticMarkup(<LiveExpressionPanel locale="zh" expression={PRESET_FACTOR_EXPRESSION} />);
    expect(preset).not.toContain("恢复预设");
    expect(preset).toContain("平台预设");
  });
});
