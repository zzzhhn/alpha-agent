"use client";

import { useState, useCallback } from "react";
import { Card, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { runStressTest } from "@/lib/api";
import type { StressTestResult } from "@/lib/types";

interface PositionInput {
  readonly ticker: string;
  readonly value: string;
}

const DEFAULT_POSITIONS: readonly PositionInput[] = [
  { ticker: "NVDA", value: "40000" },
  { ticker: "AAPL", value: "30000" },
  { ticker: "JPM", value: "20000" },
  { ticker: "XOM", value: "10000" },
];

export default function StressTestPage() {
  const { locale } = useLocale();
  const [positions, setPositions] = useState<readonly PositionInput[]>(DEFAULT_POSITIONS);
  const [scenario, setScenario] = useState("covid_crash");
  const [result, setResult] = useState<StressTestResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleRun = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    const posArray = positions
      .filter((p) => p.ticker && Number(p.value) > 0)
      .map((p) => ({ ticker: p.ticker, value: Number(p.value) }));
    if (posArray.length === 0) {
      setError(locale === "zh" ? "请至少添加一个持仓" : "Add at least one position");
      setIsLoading(false);
      return;
    }
    const res = await runStressTest({ positions: posArray, scenario });
    if (res.data) {
      setResult(res.data);
    } else {
      setError(res.error ?? "Unknown error");
    }
    setIsLoading(false);
  }, [positions, scenario, locale]);

  const updatePosition = useCallback((index: number, field: "ticker" | "value", val: string) => {
    setPositions((prev) => prev.map((p, i) => (i === index ? { ...p, [field]: field === "ticker" ? val.toUpperCase() : val } : p)));
  }, []);

  const addPosition = useCallback(() => {
    setPositions((prev) => [...prev, { ticker: "", value: "10000" }]);
  }, []);

  const removePosition = useCallback((index: number) => {
    setPositions((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const scenarioNames: Record<string, { en: string; zh: string }> = {
    covid_crash: { en: "COVID-19 Crash (2020)", zh: "新冠暴跌 (2020)" },
    rate_hike_2022: { en: "Rate Hike Selloff (2022)", zh: "加息抛售 (2022)" },
    gfc_2008: { en: "Financial Crisis (2008)", zh: "金融危机 (2008)" },
    dot_com_burst: { en: "Dot-Com Burst (2000)", zh: "互联网泡沫 (2000)" },
  };

  return (
    <div className="grid gap-4 lg:grid-cols-[380px_1fr]">
      {/* Left: Controls */}
      <div className="space-y-4 lg:sticky lg:top-0 lg:max-h-screen lg:overflow-y-auto">
        {/* Scenario Selection */}
        <Card>
          <CardHeader title={t(locale, "stress.scenario")} icon="🌪️" />
          <div className="space-y-2 p-4">
            {Object.entries(scenarioNames).map(([key, names]) => (
              <button
                key={key}
                type="button"
                onClick={() => setScenario(key)}
                className={`w-full rounded-lg border px-3 py-2.5 text-left text-sm transition-colors ${
                  scenario === key
                    ? "border-accent bg-accent/10 text-accent"
                    : "border-border text-muted hover:border-accent/50 hover:text-text"
                }`}
              >
                {locale === "zh" ? names.zh : names.en}
              </button>
            ))}
          </div>
        </Card>

        {/* Positions */}
        <Card>
          <CardHeader title={t(locale, "stress.positions")} icon="💼" />
          <div className="space-y-2 p-4">
            {positions.map((pos, i) => (
              <div key={i} className="flex items-center gap-2">
                <input
                  type="text"
                  value={pos.ticker}
                  onChange={(e) => updatePosition(i, "ticker", e.target.value)}
                  placeholder="NVDA"
                  className="w-20 rounded-lg border border-border bg-card px-2 py-1.5 font-mono text-xs text-text placeholder:text-muted/50 focus:border-accent focus:outline-none"
                />
                <input
                  type="number"
                  value={pos.value}
                  onChange={(e) => updatePosition(i, "value", e.target.value)}
                  className="flex-1 rounded-lg border border-border bg-card px-2 py-1.5 font-mono text-xs text-text focus:border-accent focus:outline-none"
                />
                <button
                  type="button"
                  onClick={() => removePosition(i)}
                  className="text-muted hover:text-red"
                  title="Remove"
                >
                  ✕
                </button>
              </div>
            ))}
            <button
              type="button"
              onClick={addPosition}
              className="w-full rounded-lg border border-dashed border-border py-1.5 text-xs text-muted transition-colors hover:border-accent hover:text-accent"
            >
              + {t(locale, "stress.addPosition")}
            </button>
          </div>
        </Card>

        <Button variant="primary" className="w-full" onClick={handleRun} disabled={isLoading}>
          {isLoading ? t(locale, "stress.running") : t(locale, "stress.run")}
        </Button>
      </div>

      {/* Right: Results */}
      <div>
        {error && (
          <div className="mb-4 rounded-lg border border-red/30 bg-red/5 p-4 text-sm text-red">{error}</div>
        )}

        {result ? (
          <div className="space-y-4">
            {/* Scenario Header */}
            <Card>
              <div className="p-4">
                <div className="text-xs text-muted">{result.scenario.period}</div>
                <div className="mt-1 text-lg font-bold text-text">
                  {locale === "zh" ? result.scenario.name_zh : result.scenario.name}
                </div>
                <div className="mt-1 text-sm text-muted">{result.scenario.description}</div>
              </div>
            </Card>

            {/* Portfolio Impact KPIs */}
            <div className="grid grid-cols-3 gap-3">
              <Card>
                <div className="p-4 text-center">
                  <div className="text-[11px] text-muted">{t(locale, "stress.portfolioImpact")}</div>
                  <div className="mt-1 text-2xl font-bold" style={{ color: result.portfolio.pnl >= 0 ? "var(--green)" : "var(--red)" }}>
                    {result.portfolio.return_pct >= 0 ? "+" : ""}{result.portfolio.return_pct}%
                  </div>
                </div>
              </Card>
              <Card>
                <div className="p-4 text-center">
                  <div className="text-[11px] text-muted">{t(locale, "stress.pnl")}</div>
                  <div className="mt-1 text-2xl font-bold" style={{ color: result.portfolio.pnl >= 0 ? "var(--green)" : "var(--red)" }}>
                    {result.portfolio.pnl >= 0 ? "+" : ""}${Math.abs(result.portfolio.pnl).toLocaleString()}
                  </div>
                </div>
              </Card>
              <Card>
                <div className="p-4 text-center">
                  <div className="text-[11px] text-muted">{locale === "zh" ? "剩余价值" : "Remaining"}</div>
                  <div className="mt-1 text-2xl font-bold text-text">
                    ${result.portfolio.final_value.toLocaleString()}
                  </div>
                </div>
              </Card>
            </div>

            {/* Waterfall-style Position Breakdown */}
            <Card>
              <CardHeader title={t(locale, "stress.positionBreakdown")} icon="📉" />
              <div className="p-4">
                {result.positions.map((pos) => {
                  const barWidth = Math.min(Math.abs(pos.shock) * 100, 100);
                  return (
                    <div key={pos.ticker} className="mb-3">
                      <div className="flex items-center justify-between text-sm">
                        <div className="flex items-center gap-2">
                          <span className="font-mono font-bold text-text">{pos.ticker}</span>
                          <span className="text-xs text-muted">${pos.value.toLocaleString()}</span>
                          <span className="text-xs text-muted">({(pos.weight * 100).toFixed(0)}%)</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <Badge variant={pos.pnl >= 0 ? "green" : "red"} size="sm">
                            {pos.pnl >= 0 ? "+" : ""}${pos.pnl.toLocaleString()}
                          </Badge>
                          <span className="font-mono text-xs" style={{ color: pos.shock >= 0 ? "var(--green)" : "var(--red)" }}>
                            {(pos.shock * 100).toFixed(1)}%
                          </span>
                        </div>
                      </div>
                      <div className="mt-1 h-2 w-full rounded-full bg-border">
                        <div
                          className="h-full rounded-full transition-all"
                          style={{
                            width: `${barWidth}%`,
                            background: pos.shock >= 0 ? "var(--green)" : "var(--red)",
                            opacity: 0.7,
                          }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </Card>
          </div>
        ) : (
          <EmptyState
            title={t(locale, "stress.title")}
            description={locale === "zh"
              ? "配置投资组合持仓，选择历史危机情景，一键查看组合在极端行情下的表现"
              : "Configure portfolio positions, select a historical crisis scenario, and see how your portfolio would perform under stress"}
            icon="🌪️"
          />
        )}
      </div>
    </div>
  );
}
