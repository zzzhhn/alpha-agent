import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { WeightDeltaTable } from "../WeightDeltaTable";
import type { ObservatoryWeight } from "../observatory-model";

// The portal needs a viewport; preserve the raw tooltip content for SSR tests.
vi.mock("@/components/ui/HoverTip", () => ({
  HoverTip: ({ children, content }: { children: ReactNode; content: string }) => <span data-tooltip={content}>{children}</span>,
}));

function weight(status: string, value: number, reason: string | null = null): ObservatoryWeight {
  return { signal_name: "signal", status, weight: value, reason, last_updated: "2026-11-10T00:00:00Z", consecutive_bad_windows: 0, shadow_streak: 0 };
}

describe("WeightDeltaTable", () => {
  it("renders a single aligned row including effective and guarded-only metadata", () => {
    const raw = '{"alpha": 0.1, "mode": "adaptive_guarded"}';
    const html = renderToStaticMarkup(<WeightDeltaTable locale="zh" weights={[
      weight("guarded_shadow", 0.4, raw), weight("shadow", 0.3), weight("effective", 0.2), weight("live", 0),
    ]} />);
    expect(html.match(/<tr /g)).toHaveLength(2);
    for (const header of ["线上 LIVE", "生效 EFFECTIVE", "影子 SHADOW", "守护影子 GUARDED"]) expect(html).toContain(header);
    const numbers = [...html.matchAll(/>(\d\.\d{4})</g)].map((match) => match[1]);
    expect(numbers).toEqual(["0.0000", "0.2000", "0.3000", "0.4000"]);
    expect(html).toContain("自适应（守护）α=0.1");
    expect(html).toContain('data-tooltip="{&quot;alpha&quot;: 0.1, &quot;mode&quot;: &quot;adaptive_guarded&quot;}"');
  });
  it("renders missing columns as dashes instead of treating effective as shadow", () => {
    const html = renderToStaticMarkup(<WeightDeltaTable locale="en" weights={[weight("effective", 0.2)]} />);
    expect(html).toContain("0.2000");
    expect(html).not.toContain("0.0000");
    expect(html.match(/>—</g)?.length).toBeGreaterThanOrEqual(3);
  });
});
