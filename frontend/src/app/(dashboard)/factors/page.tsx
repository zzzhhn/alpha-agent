"use client";

import { useState, useCallback } from "react";
import { Card, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { TickerSearch } from "@/components/ui/TickerSearch";
import { EmptyState } from "@/components/ui/EmptyState";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { analyzeFactors } from "@/lib/api";
import type { FactorAnalysisResult } from "@/lib/types";

export default function FactorsPage() {
  const { locale } = useLocale();
  const [ticker, setTicker] = useState("NVDA");
  const [sortBy, setSortBy] = useState("ic");
  const [result, setResult] = useState<FactorAnalysisResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleAnalyze = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    const res = await analyzeFactors(ticker, sortBy);
    if (res.data) {
      setResult(res.data);
    } else {
      setError(res.error ?? "Unknown error");
    }
    setIsLoading(false);
  }, [ticker, sortBy]);

  return (
    <div className="space-y-4">
      {/* Controls */}
      <Card>
        <div className="flex flex-wrap items-end gap-3 p-4">
          <div className="w-48">
            <TickerSearch
              label={t(locale, "backtest.ticker")}
              value={ticker}
              onChange={setTicker}
              placeholder="NVDA"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-[11px] text-muted">
              {locale === "zh" ? "排序" : "Sort By"}
            </label>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              className="rounded-lg border border-border bg-card px-3 py-2 text-sm text-text"
            >
              <option value="ic">IC</option>
              <option value="icir">ICIR</option>
              <option value="sharpe">Sharpe</option>
              <option value="name">{locale === "zh" ? "名称" : "Name"}</option>
            </select>
          </div>
          <Button variant="primary" onClick={handleAnalyze} disabled={isLoading || !ticker}>
            {isLoading
              ? (locale === "zh" ? "分析中..." : "Analyzing...")
              : (locale === "zh" ? "运行分析" : "Analyze")}
          </Button>
        </div>
      </Card>

      {error && (
        <div className="rounded-lg border border-red/30 bg-red/5 p-4 text-sm text-red">{error}</div>
      )}

      {result ? (
        <>
          {/* Live Feature Stats */}
          {result.feature_stats.length > 0 && (
            <Card>
              <CardHeader title={t(locale, "factors.liveStats")} icon="📊" subtitle={result.ticker} />
              <div className="overflow-x-auto p-4">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-border text-[11px] text-muted">
                      <th className="pb-2 pr-4">{locale === "zh" ? "特征" : "Feature"}</th>
                      <th className="pb-2 pr-4 text-right">{locale === "zh" ? "当前值" : "Value"}</th>
                      <th className="pb-2 pr-4 text-right">{locale === "zh" ? "均值" : "Mean"}</th>
                      <th className="pb-2 pr-4 text-right">Std</th>
                      <th className="pb-2 pr-4 text-right">Min</th>
                      <th className="pb-2 text-right">Max</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.feature_stats.map((f) => {
                      const zScore = f.std > 0 ? (f.value - f.mean) / f.std : 0;
                      return (
                        <tr key={f.name} className="border-b border-border/50">
                          <td className="py-2 pr-4 font-mono text-xs font-semibold text-accent">{f.name}</td>
                          <td className="py-2 pr-4 text-right font-mono text-xs">{f.value.toFixed(4)}</td>
                          <td className="py-2 pr-4 text-right font-mono text-xs text-muted">{f.mean.toFixed(4)}</td>
                          <td className="py-2 pr-4 text-right font-mono text-xs text-muted">{f.std.toFixed(4)}</td>
                          <td className="py-2 pr-4 text-right font-mono text-xs text-muted">{f.min.toFixed(4)}</td>
                          <td className="py-2 text-right font-mono text-xs text-muted">{f.max.toFixed(4)}</td>
                          <td className="py-2 pl-3">
                            <Badge variant={Math.abs(zScore) > 2 ? "red" : Math.abs(zScore) > 1 ? "yellow" : "green"} size="sm">
                              z={zScore.toFixed(1)}
                            </Badge>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </Card>
          )}

          {/* Correlation Matrix */}
          {result.correlation_matrix.length > 0 && (
            <Card>
              <CardHeader title={t(locale, "factors.correlation")} icon="🔗" />
              <div className="overflow-x-auto p-4">
                <table className="text-[10px]">
                  <thead>
                    <tr>
                      <th />
                      {result.feature_names.map((n) => (
                        <th key={n} className="px-1 py-1 text-muted" style={{ writingMode: "vertical-rl", maxHeight: 80 }}>
                          {n.slice(0, 8)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {result.correlation_matrix.map((row, i) => (
                      <tr key={result.feature_names[i]}>
                        <td className="pr-2 font-mono text-muted">{result.feature_names[i]?.slice(0, 8)}</td>
                        {row.map((val, j) => {
                          const abs = Math.abs(val);
                          const color = val > 0
                            ? `rgba(34, 197, 94, ${abs * 0.6})`
                            : `rgba(239, 68, 68, ${abs * 0.6})`;
                          return (
                            <td key={j} className="px-1 py-1 text-center font-mono" style={{ background: i === j ? "transparent" : color }}>
                              {i === j ? "" : val.toFixed(1)}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}

          {/* Factor Registry */}
          <Card>
            <CardHeader
              title={t(locale, "factors.registry")}
              icon="🧬"
              subtitle={`${result.total_factors} ${locale === "zh" ? "个因子" : "factors"}`}
            />
            <div className="p-4">
              {result.registry_factors.length === 0 ? (
                <p className="text-sm text-muted">{t(locale, "factors.noFactors")}</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead>
                      <tr className="border-b border-border text-[11px] text-muted">
                        <th className="pb-2 pr-4">{locale === "zh" ? "名称" : "Name"}</th>
                        <th className="pb-2 pr-4 text-right">IC</th>
                        <th className="pb-2 pr-4 text-right">ICIR</th>
                        <th className="pb-2 pr-4 text-right">Sharpe</th>
                        <th className="pb-2 text-right">Turnover</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.registry_factors.map((f) => (
                        <tr key={f.id} className="border-b border-border/50">
                          <td className="py-2 pr-4">
                            <div className="font-semibold text-text">{f.name}</div>
                            <div className="text-[10px] text-muted">{f.expression.slice(0, 40)}</div>
                          </td>
                          <td className="py-2 pr-4 text-right font-mono text-xs">{f.ic.toFixed(4)}</td>
                          <td className="py-2 pr-4 text-right font-mono text-xs">{f.icir.toFixed(4)}</td>
                          <td className="py-2 pr-4 text-right font-mono text-xs">{f.sharpe.toFixed(4)}</td>
                          <td className="py-2 text-right font-mono text-xs">{f.turnover.toFixed(4)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </Card>
        </>
      ) : (
        <EmptyState
          title={t(locale, "factors.title")}
          description={locale === "zh"
            ? "选择股票代码，查看实时特征统计、因子库和相关性矩阵"
            : "Select a ticker to view live feature stats, factor registry, and correlation matrix"}
          icon="🧬"
        />
      )}
    </div>
  );
}
