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

const DEFAULTS = {
  ticker: "NVDA" as string,
  startDate: "2024-01-01",
  endDate: "2025-01-01",
  rsiPeriod: 14,
  rsiOversold: 30,
  rsiOverbought: 70,
  macdFast: 12,
  macdSlow: 26,
  bollingerPeriod: 20,
  bollingerStd: 2.0,
  stopLoss: 0,
  takeProfit: 0,
  positionSize: 100,
};

const PARAM_GUIDES = {
  zh: {
    rsi: "RSI（相对强弱指标）衡量价格动量。周期越短越敏感。超卖线以下视为被低估（买入信号），超买线以上视为被高估（卖出信号）。经典设置：14/30/70。",
    macd: "MACD 用两条指数移动均线的差值捕捉趋势变化。快线周期越短，对价格变化越敏感。当 MACD 柱状图由负转正时，通常意味着上升趋势开始。",
    bollinger: "布林带用移动均线 ± N倍标准差构建通道。宽度(σ)越大，通道越宽，信号越少但越可靠。价格触及下轨时可能反弹。",
    risk: "止损：亏损超过设定比例自动卖出，防止单笔巨亏。止盈：盈利达到目标自动锁定利润。仓位比例：每笔交易投入的资金占比，100%为全仓。专业机构通常单笔仓位不超过 20%。",
  },
  en: {
    rsi: "RSI (Relative Strength Index) measures price momentum. Shorter periods are more sensitive. Below the oversold line suggests undervalued (buy signal), above overbought suggests overvalued (sell signal). Classic setup: 14/30/70.",
    macd: "MACD uses the difference between two EMAs to capture trend changes. Shorter fast periods react quicker. When the MACD histogram turns from negative to positive, it often signals an uptrend beginning.",
    bollinger: "Bollinger Bands use a moving average ± N standard deviations. Wider bands (higher σ) = fewer but more reliable signals. Price touching the lower band may indicate a bounce opportunity.",
    risk: "Stop Loss: auto-sell when loss exceeds threshold, preventing catastrophic losses. Take Profit: lock in gains at a target. Position Size: % of capital per trade. Professionals typically risk no more than 20% per position.",
  },
} as const;

export function BacktestForm({ onSubmit, isLoading }: BacktestFormProps) {
  const { locale } = useLocale();

  const [ticker, setTicker] = useState(DEFAULTS.ticker);
  const [startDate, setStartDate] = useState(DEFAULTS.startDate);
  const [endDate, setEndDate] = useState(DEFAULTS.endDate);
  const [rsiPeriod, setRsiPeriod] = useState(DEFAULTS.rsiPeriod);
  const [rsiOversold, setRsiOversold] = useState(DEFAULTS.rsiOversold);
  const [rsiOverbought, setRsiOverbought] = useState(DEFAULTS.rsiOverbought);
  const [macdFast, setMacdFast] = useState(DEFAULTS.macdFast);
  const [macdSlow, setMacdSlow] = useState(DEFAULTS.macdSlow);
  const [bollingerPeriod, setBollingerPeriod] = useState(DEFAULTS.bollingerPeriod);
  const [bollingerStd, setBollingerStd] = useState(DEFAULTS.bollingerStd);
  const [stopLoss, setStopLoss] = useState(DEFAULTS.stopLoss);
  const [takeProfit, setTakeProfit] = useState(DEFAULTS.takeProfit);
  const [positionSize, setPositionSize] = useState(DEFAULTS.positionSize);
  const [guideOpen, setGuideOpen] = useState(false);
  const [dateError, setDateError] = useState<string | null>(null);

  const DATA_MIN = "2010-01-01";
  const today = new Date().toISOString().slice(0, 10);

  const validateDates = useCallback((): boolean => {
    if (startDate < DATA_MIN) {
      setDateError(locale === "zh"
        ? `数据最早可用日期为 ${DATA_MIN}，请调整开始日期`
        : `Data available from ${DATA_MIN}. Please adjust start date.`);
      return false;
    }
    if (endDate > today) {
      setDateError(locale === "zh"
        ? `结束日期不能晚于今天 (${today})`
        : `End date cannot be later than today (${today}).`);
      return false;
    }
    if (startDate >= endDate) {
      setDateError(locale === "zh"
        ? "开始日期必须早于结束日期"
        : "Start date must be before end date.");
      return false;
    }
    setDateError(null);
    return true;
  }, [startDate, endDate, locale, today]);

  const handleReset = useCallback(() => {
    setDateError(null);
    setTicker(DEFAULTS.ticker);
    setStartDate(DEFAULTS.startDate);
    setEndDate(DEFAULTS.endDate);
    setRsiPeriod(DEFAULTS.rsiPeriod);
    setRsiOversold(DEFAULTS.rsiOversold);
    setRsiOverbought(DEFAULTS.rsiOverbought);
    setMacdFast(DEFAULTS.macdFast);
    setMacdSlow(DEFAULTS.macdSlow);
    setBollingerPeriod(DEFAULTS.bollingerPeriod);
    setBollingerStd(DEFAULTS.bollingerStd);
    setStopLoss(DEFAULTS.stopLoss);
    setTakeProfit(DEFAULTS.takeProfit);
    setPositionSize(DEFAULTS.positionSize);
  }, []);

  const handleSubmit = useCallback(() => {
    if (!validateDates()) return;
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
      bollinger_std: bollingerStd,
      stop_loss_pct: stopLoss,
      take_profit_pct: takeProfit,
      position_size_pct: positionSize,
    });
  }, [
    ticker, startDate, endDate, rsiPeriod, rsiOversold,
    rsiOverbought, macdFast, macdSlow, bollingerPeriod,
    bollingerStd, stopLoss, takeProfit, positionSize, onSubmit, validateDates,
  ]);

  const guides = PARAM_GUIDES[locale];

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

        {dateError && (
          <div className="rounded-lg border border-red/30 bg-red/5 px-3 py-2 text-xs text-red">
            {dateError}
          </div>
        )}

        {/* RSI */}
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

        {/* MACD */}
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

        {/* Bollinger Bands */}
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
          <Slider
            label={t(locale, "backtest.bollingerStd")}
            value={bollingerStd}
            min={0.5}
            max={4.0}
            step={0.1}
            onChange={setBollingerStd}
          />
        </div>

        {/* Risk Management */}
        <div className="border-t border-border pt-3">
          <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted">
            {locale === "zh" ? "风险管理" : "Risk Management"}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Slider
              label={t(locale, "backtest.stopLoss")}
              value={stopLoss}
              min={0}
              max={30}
              step={0.5}
              onChange={setStopLoss}
              unit="%"
            />
            <Slider
              label={t(locale, "backtest.takeProfit")}
              value={takeProfit}
              min={0}
              max={50}
              step={0.5}
              onChange={setTakeProfit}
              unit="%"
            />
          </div>
          <Slider
            label={t(locale, "backtest.positionSize")}
            value={positionSize}
            min={10}
            max={100}
            step={5}
            onChange={setPositionSize}
            unit="%"
          />
        </div>

        {/* Submit + Reset */}
        <div className="flex gap-2">
          <Button
            variant="primary"
            className="flex-1"
            onClick={handleSubmit}
            disabled={isLoading || !ticker}
          >
            {isLoading
              ? t(locale, "backtest.running")
              : t(locale, "backtest.run")}
          </Button>
          <button
            type="button"
            onClick={handleReset}
            className="rounded-lg border border-border px-3 py-2 text-xs text-muted transition-colors hover:bg-white/5 hover:text-text"
            title={t(locale, "backtest.resetDefaults")}
          >
            ↺
          </button>
        </div>

        {/* Parameter Guide (collapsible) */}
        <div className="border-t border-border pt-3">
          <button
            type="button"
            onClick={() => setGuideOpen((prev) => !prev)}
            className="flex w-full items-center justify-between text-left text-[11px] font-semibold uppercase tracking-wide text-muted transition-colors hover:text-text"
          >
            <span>{t(locale, "backtest.paramGuide")}</span>
            <span className="text-sm transition-transform" style={{ transform: guideOpen ? "rotate(180deg)" : "rotate(0deg)" }}>
              ▾
            </span>
          </button>

          {guideOpen && (
            <div className="mt-3 space-y-3 text-xs leading-relaxed text-muted">
              <div>
                <div className="mb-1 font-semibold text-text">RSI</div>
                <p>{guides.rsi}</p>
              </div>
              <div>
                <div className="mb-1 font-semibold text-text">MACD</div>
                <p>{guides.macd}</p>
              </div>
              <div>
                <div className="mb-1 font-semibold text-text">Bollinger Bands</div>
                <p>{guides.bollinger}</p>
              </div>
              <div>
                <div className="mb-1 font-semibold text-text">
                  {locale === "zh" ? "风险管理" : "Risk Management"}
                </div>
                <p>{guides.risk}</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}
