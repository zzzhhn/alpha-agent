"use client";

import { useState, useCallback } from "react";
import { BacktestForm } from "@/components/backtest/BacktestForm";
import { BacktestResults } from "@/components/backtest/BacktestResults";
import { EmptyState } from "@/components/ui/EmptyState";
import { runBacktest } from "@/lib/api";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import type { BacktestRequest, BacktestResult } from "@/lib/types";

export default function BacktestPage() {
  const { locale } = useLocale();
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = useCallback(async (params: BacktestRequest) => {
    setIsLoading(true);
    setError(null);

    const res = await runBacktest(params);

    if (res.data) {
      setResult(res.data);
    } else {
      setError(res.error ?? "Unknown error");
    }

    setIsLoading(false);
  }, []);

  return (
    <div className="grid gap-4 lg:grid-cols-[340px_1fr]">
      {/* Left: Form Panel */}
      <div className="lg:sticky lg:top-0 lg:max-h-screen lg:overflow-y-auto">
        <BacktestForm onSubmit={handleSubmit} isLoading={isLoading} />
      </div>

      {/* Right: Results */}
      <div>
        {error && (
          <div className="mb-4 rounded-lg border border-red/30 bg-red/5 p-4 text-sm text-red">
            {error}
          </div>
        )}

        {result ? (
          <BacktestResults result={result} />
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
