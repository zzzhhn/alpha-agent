"use client";

import { useState, useCallback, useEffect } from "react";
import { BacktestForm } from "@/components/backtest/BacktestForm";
import { BacktestResults } from "@/components/backtest/BacktestResults";
import { BacktestHistoryPanel } from "@/components/backtest/BacktestHistoryPanel";
import { EmptyState } from "@/components/ui/EmptyState";
import { runBacktest } from "@/lib/api";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import {
  addToHistory,
  getFavorites,
  getRecent,
  removeFromHistory,
  toggleFavorite,
} from "@/lib/backtest-history";
import type {
  BacktestHistoryEntry,
  BacktestRequest,
  BacktestResult,
} from "@/lib/types";

export default function BacktestPage() {
  const { locale } = useLocale();
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [favorites, setFavorites] = useState<readonly BacktestHistoryEntry[]>(
    []
  );
  const [recent, setRecent] = useState<readonly BacktestHistoryEntry[]>([]);

  // Hydrate history from localStorage after mount (SSR-safe)
  useEffect(() => {
    setFavorites(getFavorites());
    setRecent(getRecent());
  }, []);

  const refreshHistory = useCallback(() => {
    setFavorites(getFavorites());
    setRecent(getRecent());
  }, []);

  const handleSubmit = useCallback(
    async (params: BacktestRequest) => {
      setIsLoading(true);
      setError(null);

      const res = await runBacktest(params);

      if (res.data) {
        const entry = addToHistory(params, res.data);
        setResult(res.data);
        setActiveId(entry.id);
        refreshHistory();
      } else {
        setError(res.error ?? "Unknown error");
      }

      setIsLoading(false);
    },
    [refreshHistory]
  );

  const handleLoadEntry = useCallback((entry: BacktestHistoryEntry) => {
    setResult(entry.result);
    setActiveId(entry.id);
    setError(null);
  }, []);

  const handleToggleFavorite = useCallback(
    (id: string) => {
      toggleFavorite(id);
      refreshHistory();
    },
    [refreshHistory]
  );

  const handleRemove = useCallback(
    (id: string) => {
      removeFromHistory(id);
      if (activeId === id) {
        setActiveId(null);
        setResult(null);
      }
      refreshHistory();
    },
    [activeId, refreshHistory]
  );

  const handleToggleActiveFavorite = useCallback(() => {
    if (activeId) {
      handleToggleFavorite(activeId);
    }
  }, [activeId, handleToggleFavorite]);

  const activeIsFavorite = activeId
    ? favorites.some((e) => e.id === activeId)
    : false;

  return (
    <div className="grid gap-4 lg:grid-cols-[340px_1fr]">
      {/* Left: Form + History Panel */}
      <div className="space-y-4 lg:sticky lg:top-0 lg:max-h-screen lg:overflow-y-auto lg:pb-4">
        <BacktestForm onSubmit={handleSubmit} isLoading={isLoading} />
        <BacktestHistoryPanel
          favorites={favorites}
          recent={recent}
          activeId={activeId}
          onLoad={handleLoadEntry}
          onToggleFavorite={handleToggleFavorite}
          onRemove={handleRemove}
        />
      </div>

      {/* Right: Results */}
      <div>
        {error && (
          <div className="mb-4 rounded-lg border border-red/30 bg-red/5 p-4 text-sm text-red">
            {error}
          </div>
        )}

        {result ? (
          <BacktestResults
            result={result}
            isFavorite={activeIsFavorite}
            onToggleFavorite={activeId ? handleToggleActiveFavorite : undefined}
          />
        ) : (
          <EmptyState
            title={t(locale, "backtest.title")}
            description={
              locale === "zh"
                ? "选择股票代码，调整策略参数，点击「运行回测」查看结果"
                : "Select a ticker, adjust strategy parameters, and click Run Backtest to see results"
            }
            icon="\uD83D\uDCC9"
          />
        )}
      </div>
    </div>
  );
}
