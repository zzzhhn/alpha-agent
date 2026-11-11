import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { IcTrendChart } from "../IcTrendChart";

// ResponsiveContainer cannot measure a browser viewport in Node. Preserve
// chart children and expose Line configuration to test the rendering decision.
vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  LineChart: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  Line: ({ dataKey, strokeWidth, dot }: { dataKey: string; strokeWidth: number; dot: (props: object) => ReactNode }) => (
    <svg data-signal={dataKey} data-stroke-width={strokeWidth}>
      {dot({ cx: 10, cy: 20, stroke: "red", payload: { _ts: "2026-11-01", [dataKey]: 0.1 } })}
    </svg>
  ),
  XAxis: () => null, YAxis: () => null, CartesianGrid: () => null,
  Tooltip: () => null, ReferenceLine: () => null, Legend: () => null,
}));

const series = (signal_name: string, n: number) => ({ signal_name, points: Array.from({ length: n }, (_, i) => ({ computed_at: `2026-11-0${i + 1}`, ic: 0.1, n: 10 })) });

describe("IcTrendChart sparse series", () => {
  it("renders all sparse points with no visible line and an inline warning", () => {
    const html = renderToStaticMarkup(<IcTrendChart locale="zh" series={[series("sparse", 2)]} />);
    expect(html).toContain("观测不足（2 个点），不构成趋势");
    expect(html).toContain('data-stroke-width="0"');
    expect(html).toContain("<circle");
  });
  it("applies the threshold per series and restores the line at five points", () => {
    const html = renderToStaticMarkup(<IcTrendChart locale="en" series={[series("sparse", 4), series("enough", 5)]} />);
    expect(html).toContain("Too few observations (4); not a trend");
    expect(html).not.toContain("Too few observations (5)");
    expect(html).toContain('data-signal="enough" data-stroke-width="2"');
    expect(html).toContain('data-signal="sparse" data-stroke-width="0"');
  });
});
