"use client";

import { useEffect, useRef, useState } from "react";
import { Card } from "@/components/ui/Card";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import type { CoverageResponse } from "@/lib/types";

interface CoverageHeatmapProps {
  readonly coverage: CoverageResponse;
}

// Dimensions chosen so a 250 x 36 panel renders crisp on retina without
// horizontal scroll on a typical desktop viewport.
const CELL_W = 3;
const CELL_H = 10;
const ROW_GAP = 1;

export function CoverageHeatmap({ coverage }: CoverageHeatmapProps) {
  const { locale } = useLocale();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [hover, setHover] = useState<{
    ticker: string;
    date: string;
    present: boolean;
    x: number;
    y: number;
  } | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const T = coverage.dates.length;
    const N = coverage.tickers.length;
    const dpr = window.devicePixelRatio ?? 1;
    const widthCss = T * CELL_W;
    const heightCss = N * (CELL_H + ROW_GAP);

    canvas.width = widthCss * dpr;
    canvas.height = heightCss * dpr;
    canvas.style.width = `${widthCss}px`;
    canvas.style.height = `${heightCss}px`;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.scale(dpr, dpr);

    // matrix is (T rows) x (N cols) from backend. Transpose visually so each
    // row is a ticker and x-axis is time — reading direction matches research
    // convention.
    for (let t = 0; t < T; t++) {
      const col = coverage.matrix[t];
      for (let n = 0; n < N; n++) {
        const present = col[n] === 1;
        ctx.fillStyle = present
          ? "rgba(74, 222, 128, 0.85)"
          : "rgba(148, 163, 184, 0.35)";
        ctx.fillRect(t * CELL_W, n * (CELL_H + ROW_GAP), CELL_W, CELL_H);
      }
    }
  }, [coverage]);

  function onMove(e: React.MouseEvent<HTMLCanvasElement>) {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const t = Math.floor(x / CELL_W);
    const n = Math.floor(y / (CELL_H + ROW_GAP));
    if (t < 0 || t >= coverage.dates.length) {
      setHover(null);
      return;
    }
    if (n < 0 || n >= coverage.tickers.length) {
      setHover(null);
      return;
    }
    setHover({
      ticker: coverage.tickers[n],
      date: coverage.dates[t],
      present: coverage.matrix[t][n] === 1,
      x,
      y,
    });
  }

  return (
    <Card padding="md">
      <header className="mb-3">
        <h2 className="text-sm font-semibold text-text">
          {t(locale, "data.coverage.title")}
        </h2>
        <p className="mt-1 text-[11px] leading-relaxed text-muted">
          {t(locale, "data.coverage.subtitle")}
        </p>
      </header>

      <div className="mb-3 flex gap-6 text-[11px]">
        <Kpi
          label={t(locale, "data.coverage.total")}
          value={coverage.total_cells.toLocaleString()}
        />
        <Kpi
          label={t(locale, "data.coverage.missing")}
          value={coverage.missing_cells.toLocaleString()}
          accent={coverage.missing_cells > 0 ? "red" : "green"}
        />
        <Kpi
          label={t(locale, "data.coverage.pct")}
          value={`${coverage.coverage_pct.toFixed(2)}%`}
          accent="green"
        />
      </div>

      <div className="relative overflow-x-auto rounded-md border border-border bg-[var(--toggle-bg)] p-2">
        <canvas
          ref={canvasRef}
          onMouseMove={onMove}
          onMouseLeave={() => setHover(null)}
          className="block cursor-crosshair"
        />
        {hover && (
          <div
            className="pointer-events-none absolute z-10 rounded-md border border-border bg-[var(--card-bg)] px-2 py-1 font-mono text-[10px] text-text shadow-sm"
            style={{ left: hover.x + 12, top: hover.y + 12 }}
          >
            <div>
              <span className="text-muted">ticker:</span> {hover.ticker}
            </div>
            <div>
              <span className="text-muted">date:</span> {hover.date}
            </div>
            <div className={hover.present ? "text-green" : "text-red"}>
              {hover.present ? "present" : "missing"}
            </div>
          </div>
        )}
      </div>

      <p className="mt-2 text-[10px] text-muted">
        {t(locale, "data.coverage.legend")}
      </p>
    </Card>
  );
}

function Kpi({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: "red" | "green";
}) {
  const color =
    accent === "red"
      ? "text-red"
      : accent === "green"
        ? "text-green"
        : "text-text";
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-muted">{label}</div>
      <div className={`mt-0.5 font-mono text-sm ${color}`}>{value}</div>
    </div>
  );
}
