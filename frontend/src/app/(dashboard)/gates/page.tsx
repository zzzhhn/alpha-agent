"use client";

import { useState, useCallback } from "react";
import { Card, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Slider } from "@/components/ui/Slider";
import { TickerSearch } from "@/components/ui/TickerSearch";
import { EmptyState } from "@/components/ui/EmptyState";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { simulateGates } from "@/lib/api";
import type { GateSimulationResult } from "@/lib/types";

export default function GatesPage() {
  const { locale } = useLocale();
  const [ticker, setTicker] = useState("NVDA");
  const [threshold, setThreshold] = useState(0.5);
  const [wTrend, setWTrend] = useState(0.40);
  const [wMomentum, setWMomentum] = useState(0.35);
  const [wEntry, setWEntry] = useState(0.25);
  const [result, setResult] = useState<GateSimulationResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSimulate = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    const res = await simulateGates({
      ticker,
      gate_threshold: threshold,
      weight_trend: wTrend,
      weight_momentum: wMomentum,
      weight_entry: wEntry,
    });
    if (res.data) {
      setResult(res.data);
    } else {
      setError(res.error ?? "Unknown error");
    }
    setIsLoading(false);
  }, [ticker, threshold, wTrend, wMomentum, wEntry]);

  return (
    <div className="grid gap-4 lg:grid-cols-[340px_1fr]">
      {/* Left: Controls */}
      <div className="space-y-4 lg:sticky lg:top-0 lg:max-h-screen lg:overflow-y-auto">
        <Card>
          <CardHeader title={t(locale, "gates.title")} icon="🚦" />
          <div className="space-y-4 p-4">
            <TickerSearch
              label={t(locale, "backtest.ticker")}
              value={ticker}
              onChange={setTicker}
              placeholder="NVDA"
            />

            <Slider
              label={t(locale, "gates.threshold")}
              value={threshold}
              min={0}
              max={1}
              step={0.05}
              onChange={setThreshold}
            />

            <div className="border-t border-border pt-3">
              <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted">
                {t(locale, "gates.weights")}
              </div>
              <Slider
                label={t(locale, "gates.trend")}
                value={wTrend}
                min={0}
                max={1}
                step={0.05}
                onChange={setWTrend}
              />
              <Slider
                label={t(locale, "gates.momentum")}
                value={wMomentum}
                min={0}
                max={1}
                step={0.05}
                onChange={setWMomentum}
              />
              <Slider
                label={t(locale, "gates.entry")}
                value={wEntry}
                min={0}
                max={1}
                step={0.05}
                onChange={setWEntry}
              />
            </div>

            <Button variant="primary" className="w-full" onClick={handleSimulate} disabled={isLoading || !ticker}>
              {isLoading ? t(locale, "gates.simulating") : t(locale, "gates.simulate")}
            </Button>
          </div>
        </Card>
      </div>

      {/* Right: Results */}
      <div>
        {error && (
          <div className="mb-4 rounded-lg border border-red/30 bg-red/5 p-4 text-sm text-red">{error}</div>
        )}

        {result ? (
          <div className="space-y-4">
            {/* Overall Status */}
            <Card>
              <div className="flex items-center justify-between p-4">
                <div>
                  <div className="text-sm text-muted">{t(locale, "gates.composite")}</div>
                  <div className="mt-1 text-3xl font-bold text-text">
                    {(result.composite_score * 100).toFixed(1)}%
                  </div>
                  <div className="mt-1 text-xs text-muted">{result.signal_description}</div>
                </div>
                <Badge
                  variant={result.passed ? "green" : "red"}
                  size="lg"
                >
                  {result.passed ? t(locale, "gates.passed") : t(locale, "gates.failed")}
                </Badge>
              </div>
              {/* Threshold bar */}
              <div className="px-4 pb-4">
                <div className="relative h-3 w-full rounded-full bg-border">
                  <div
                    className="absolute left-0 top-0 h-full rounded-full transition-all"
                    style={{
                      width: `${Math.min(result.composite_score * 100, 100)}%`,
                      background: result.passed ? "var(--green)" : "var(--red)",
                    }}
                  />
                  <div
                    className="absolute top-0 h-full w-0.5 bg-text"
                    style={{ left: `${result.threshold * 100}%` }}
                    title={`Threshold: ${result.threshold}`}
                  />
                </div>
                <div className="mt-1 flex justify-between text-[10px] text-muted">
                  <span>0%</span>
                  <span>{locale === "zh" ? "阈值" : "Threshold"}: {(result.threshold * 100).toFixed(0)}%</span>
                  <span>100%</span>
                </div>
              </div>
            </Card>

            {/* Individual Gates */}
            <div className="grid gap-3 md:grid-cols-3">
              {result.gates.map((gate) => (
                <Card key={gate.name}>
                  <div className="p-4">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold text-muted">{gate.timeframe}</span>
                      <Badge variant={gate.passed ? "green" : "red"} size="sm">
                        {gate.passed ? "PASS" : "FAIL"}
                      </Badge>
                    </div>
                    <div className="mt-2 text-lg font-bold text-text">
                      {(gate.score * 100).toFixed(1)}%
                    </div>
                    <div className="mt-1 text-[11px] text-muted">{gate.name}</div>
                    <div className="mt-2 text-[10px] text-muted">{gate.description}</div>
                    {/* Score bar */}
                    <div className="mt-2 h-1.5 w-full rounded-full bg-border">
                      <div
                        className="h-full rounded-full transition-all"
                        style={{
                          width: `${Math.min(gate.score * 100, 100)}%`,
                          background: gate.passed ? "var(--green)" : "var(--red)",
                        }}
                      />
                    </div>
                    <div className="mt-1 text-[10px] text-muted">
                      {locale === "zh" ? "权重" : "Weight"}: {(gate.weight * 100).toFixed(0)}%
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          </div>
        ) : (
          <EmptyState
            title={t(locale, "gates.title")}
            description={locale === "zh"
              ? "选择股票，调整门控阈值和权重，实时查看多时间框架信号评估"
              : "Select a ticker, adjust gate threshold and weights, see real-time multi-timeframe signal evaluation"}
            icon="🚦"
          />
        )}
      </div>
    </div>
  );
}
