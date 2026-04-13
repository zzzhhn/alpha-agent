"use client";

import { useState, useCallback } from "react";
import { Card, CardHeader } from "@/components/ui/Card";
import { TickerSearch } from "@/components/ui/TickerSearch";
import { Input } from "@/components/ui/Input";
import { Slider } from "@/components/ui/Slider";
import { Button } from "@/components/ui/Button";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import type { BacktestRequest } from "@/lib/types";

interface BacktestFormProps {
  readonly onSubmit: (params: BacktestRequest) => void;
  readonly isLoading: boolean;
}

export function BacktestForm({ onSubmit, isLoading }: BacktestFormProps) {
  const { locale } = useLocale();

  const [ticker, setTicker] = useState("NVDA");
  const [startDate, setStartDate] = useState("2024-01-01");
  const [endDate, setEndDate] = useState("2025-01-01");
  const [rsiPeriod, setRsiPeriod] = useState(14);
  const [rsiOversold, setRsiOversold] = useState(30);
  const [rsiOverbought, setRsiOverbought] = useState(70);
  const [macdFast, setMacdFast] = useState(12);
  const [macdSlow, setMacdSlow] = useState(26);
  const [bollingerPeriod, setBollingerPeriod] = useState(20);

  const handleSubmit = useCallback(() => {
    onSubmit({
      ticker,
      start_date: startDate,
      end_date: endDate,
      rsi_period: rsiPeriod,
      rsi_oversold: rsiOversold,
      rsi_overbought: rsiOverbought,
      macd_fast: macdFast,
      macd_slow: macdSlow,
      bollinger_period: bollingerPeriod,
    });
  }, [
    ticker, startDate, endDate, rsiPeriod, rsiOversold,
    rsiOverbought, macdFast, macdSlow, bollingerPeriod, onSubmit,
  ]);

  return (
    <Card>
      <CardHeader
        title={t(locale, "backtest.params")}
        icon="⚙️"
      />
      <div className="space-y-4 p-4">
        {/* Ticker + Date Range */}
        <TickerSearch
          label={t(locale, "backtest.ticker")}
          value={ticker}
          onChange={setTicker}
          placeholder={t(locale, "backtest.searchTicker")}
        />

        <div className="grid grid-cols-2 gap-3">
          <Input
            label={t(locale, "backtest.startDate")}
            type="date"
            value={startDate}
            onChange={setStartDate}
          />
          <Input
            label={t(locale, "backtest.endDate")}
            type="date"
            value={endDate}
            onChange={setEndDate}
          />
        </div>

        {/* Indicator Parameters */}
        <div className="border-t border-border pt-3">
          <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted">
            RSI
          </div>
          <Slider
            label={t(locale, "backtest.rsiPeriod")}
            value={rsiPeriod}
            min={2}
            max={50}
            onChange={setRsiPeriod}
          />
          <div className="mt-2 grid grid-cols-2 gap-3">
            <Slider
              label={t(locale, "backtest.rsiOversold")}
              value={rsiOversold}
              min={10}
              max={45}
              onChange={setRsiOversold}
            />
            <Slider
              label={t(locale, "backtest.rsiOverbought")}
              value={rsiOverbought}
              min={55}
              max={90}
              onChange={setRsiOverbought}
            />
          </div>
        </div>

        <div className="border-t border-border pt-3">
          <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted">
            MACD
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Slider
              label={t(locale, "backtest.macdFast")}
              value={macdFast}
              min={2}
              max={30}
              onChange={setMacdFast}
            />
            <Slider
              label={t(locale, "backtest.macdSlow")}
              value={macdSlow}
              min={10}
              max={50}
              onChange={setMacdSlow}
            />
          </div>
        </div>

        <div className="border-t border-border pt-3">
          <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted">
            Bollinger Bands
          </div>
          <Slider
            label={t(locale, "backtest.bollingerPeriod")}
            value={bollingerPeriod}
            min={5}
            max={50}
            onChange={setBollingerPeriod}
          />
        </div>

        {/* Submit */}
        <Button
          variant="primary"
          className="w-full"
          onClick={handleSubmit}
          disabled={isLoading || !ticker}
        >
          {isLoading
            ? t(locale, "backtest.running")
            : t(locale, "backtest.run")}
        </Button>
      </div>
    </Card>
  );
}
