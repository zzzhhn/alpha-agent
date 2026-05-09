/**
 * Pure-client risk + return statistics for /report v3 panes.
 *
 * All inputs are equity curves (`{date, value}[]`) from a backtest
 * response. Outputs follow CFA Performance Standards naming where
 * applicable (Sortino, Calmar, IR, TE) so the surfaced numbers map
 * directly to institutional convention.
 *
 * No backend round-trip — every metric below derives from the daily
 * equity series already on `result.equity_curve` /
 * `result.benchmark_curve`.
 */

import type { EquityCurvePoint } from "@/lib/types";

const TRADING_DAYS_PER_YEAR = 252;

export function dailyReturns(eq: readonly EquityCurvePoint[]): readonly number[] {
  const out: number[] = [];
  for (let i = 1; i < eq.length; i++) {
    out.push(eq[i].value / eq[i - 1].value - 1);
  }
  return out;
}

export function mean(xs: readonly number[]): number {
  if (xs.length === 0) return 0;
  let s = 0;
  for (const x of xs) s += x;
  return s / xs.length;
}

export function stdev(xs: readonly number[], sample = true): number {
  if (xs.length < 2) return 0;
  const m = mean(xs);
  let ss = 0;
  for (const x of xs) ss += (x - m) ** 2;
  return Math.sqrt(ss / (sample ? xs.length - 1 : xs.length));
}

/** Annualized Sortino ratio: mean / downside_dev × √252. Downside
 *  deviation is std of returns ≤ 0 only (target=0 convention). */
export function sortinoRatio(returns: readonly number[]): number {
  if (returns.length === 0) return 0;
  const m = mean(returns);
  const downside = returns.filter((r) => r < 0);
  if (downside.length === 0) return 0;
  let ss = 0;
  for (const r of downside) ss += r ** 2;
  const dd = Math.sqrt(ss / downside.length);
  if (dd === 0) return 0;
  return (m / dd) * Math.sqrt(TRADING_DAYS_PER_YEAR);
}

/** Calmar ratio: annualized return / |max drawdown|. */
export function calmarRatio(eq: readonly EquityCurvePoint[]): number {
  if (eq.length < 2) return 0;
  const totalRet = eq[eq.length - 1].value / eq[0].value - 1;
  const years = (eq.length - 1) / TRADING_DAYS_PER_YEAR;
  const annualRet = years > 0 ? Math.pow(1 + totalRet, 1 / years) - 1 : 0;
  let peak = eq[0].value;
  let maxDD = 0;
  for (const p of eq) {
    if (p.value > peak) peak = p.value;
    const dd = (p.value - peak) / peak;
    if (dd < maxDD) maxDD = dd;
  }
  if (maxDD === 0) return 0;
  return annualRet / Math.abs(maxDD);
}

/** Active return = factor return − benchmark return per day. */
export function activeReturns(
  factor: readonly EquityCurvePoint[],
  bench: readonly EquityCurvePoint[],
): readonly number[] {
  const benchMap = new Map(bench.map((p) => [p.date, p.value]));
  const fRet = dailyReturns(factor);
  const bRet: number[] = [];
  let lastB: number | null = null;
  for (let i = 1; i < factor.length; i++) {
    const prev = benchMap.get(factor[i - 1].date) ?? lastB;
    const curr = benchMap.get(factor[i].date);
    if (prev != null && curr != null && prev > 0) {
      bRet.push(curr / prev - 1);
      lastB = curr;
    } else {
      bRet.push(0);
    }
  }
  return fRet.map((r, i) => r - (bRet[i] ?? 0));
}

/** Tracking Error: annualized std of active returns × √252. */
export function trackingError(active: readonly number[]): number {
  return stdev(active) * Math.sqrt(TRADING_DAYS_PER_YEAR);
}

/** Information Ratio: annualized mean active / TE. */
export function informationRatio(active: readonly number[]): number {
  const te = trackingError(active);
  if (te === 0) return 0;
  return (mean(active) * TRADING_DAYS_PER_YEAR) / te;
}

/** Sample skewness (Fisher-Pearson, bias-corrected via n/((n-1)(n-2))). */
export function skewness(xs: readonly number[]): number {
  const n = xs.length;
  if (n < 3) return 0;
  const m = mean(xs);
  const s = stdev(xs);
  if (s === 0) return 0;
  let cube = 0;
  for (const x of xs) cube += ((x - m) / s) ** 3;
  return (n / ((n - 1) * (n - 2))) * cube;
}

/** Excess kurtosis (Pearson): kurt - 3, bias-corrected. Mesokurtic → 0. */
export function excessKurtosis(xs: readonly number[]): number {
  const n = xs.length;
  if (n < 4) return 0;
  const m = mean(xs);
  const s = stdev(xs);
  if (s === 0) return 0;
  let q = 0;
  for (const x of xs) q += ((x - m) / s) ** 4;
  const num = (n * (n + 1)) / ((n - 1) * (n - 2) * (n - 3));
  const adj = (3 * (n - 1) ** 2) / ((n - 2) * (n - 3));
  return num * q - adj;
}

/** Historical VaR at confidence level α (e.g., 0.05 = 5% worst day). */
export function valueAtRisk(returns: readonly number[], alpha: number): number {
  if (returns.length === 0) return 0;
  const sorted = [...returns].sort((a, b) => a - b);
  const idx = Math.max(0, Math.floor(sorted.length * alpha) - 1);
  return sorted[idx] ?? 0;
}

/** Historical CVaR (Expected Shortfall): mean of returns ≤ VaR_α. */
export function conditionalVaR(returns: readonly number[], alpha: number): number {
  if (returns.length === 0) return 0;
  const sorted = [...returns].sort((a, b) => a - b);
  const cutoff = Math.max(1, Math.ceil(sorted.length * alpha));
  let s = 0;
  for (let i = 0; i < cutoff; i++) s += sorted[i];
  return s / cutoff;
}

/** Longest consecutive run of strictly-negative daily returns. */
export function maxLossStreak(returns: readonly number[]): number {
  let cur = 0;
  let best = 0;
  for (const r of returns) {
    if (r < 0) {
      cur += 1;
      if (cur > best) best = cur;
    } else {
      cur = 0;
    }
  }
  return best;
}

/** Longest consecutive run of strictly-positive daily returns. */
export function maxWinStreak(returns: readonly number[]): number {
  let cur = 0;
  let best = 0;
  for (const r of returns) {
    if (r > 0) {
      cur += 1;
      if (cur > best) best = cur;
    } else {
      cur = 0;
    }
  }
  return best;
}

/** Pearson correlation between two equal-length series. */
export function pearsonCorr(a: readonly number[], b: readonly number[]): number {
  const n = Math.min(a.length, b.length);
  if (n < 2) return 0;
  const ma = mean(a.slice(0, n));
  const mb = mean(b.slice(0, n));
  let num = 0, da = 0, db = 0;
  for (let i = 0; i < n; i++) {
    const xa = a[i] - ma;
    const xb = b[i] - mb;
    num += xa * xb;
    da += xa * xa;
    db += xb * xb;
  }
  const denom = Math.sqrt(da * db);
  return denom === 0 ? 0 : num / denom;
}

/** Rolling Pearson correlation, window-aligned to the right edge.
 *  Output length = inputs.length − window + 1; first window-1 are dropped. */
export function rollingCorr(
  a: readonly number[],
  b: readonly number[],
  window: number,
): readonly { i: number; corr: number }[] {
  const n = Math.min(a.length, b.length);
  const out: { i: number; corr: number }[] = [];
  if (n < window) return out;
  for (let end = window - 1; end < n; end++) {
    const start = end - window + 1;
    const c = pearsonCorr(
      a.slice(start, end + 1),
      b.slice(start, end + 1),
    );
    out.push({ i: end, corr: c });
  }
  return out;
}

/** Per-year aggregation: bucket equity curve by date.year, return
 *  per-year SR / total return / max drawdown / hit-rate. */
export interface YearStats {
  readonly year: number;
  readonly nDays: number;
  readonly sharpe: number;
  readonly totalReturn: number;
  readonly maxDrawdown: number;
  readonly hitRate: number;
}
export function yearlyStats(
  eq: readonly EquityCurvePoint[],
): readonly YearStats[] {
  if (eq.length < 2) return [];
  const byYear = new Map<number, EquityCurvePoint[]>();
  for (const p of eq) {
    const y = parseInt(p.date.slice(0, 4), 10);
    if (!Number.isFinite(y)) continue;
    if (!byYear.has(y)) byYear.set(y, []);
    byYear.get(y)!.push(p);
  }
  const years = Array.from(byYear.keys()).sort();
  const out: YearStats[] = [];
  for (const y of years) {
    const slice = byYear.get(y)!;
    if (slice.length < 2) continue;
    const rets = dailyReturns(slice);
    const m = mean(rets);
    const s = stdev(rets);
    const sr = s > 0 ? (m / s) * Math.sqrt(TRADING_DAYS_PER_YEAR) : 0;
    const tr = slice[slice.length - 1].value / slice[0].value - 1;
    let peak = slice[0].value;
    let maxDD = 0;
    for (const p of slice) {
      if (p.value > peak) peak = p.value;
      const dd = (p.value - peak) / peak;
      if (dd < maxDD) maxDD = dd;
    }
    const hit = rets.length > 0
      ? rets.filter((r) => r > 0).length / rets.length
      : 0;
    out.push({
      year: y,
      nDays: rets.length,
      sharpe: sr,
      totalReturn: tr,
      maxDrawdown: maxDD,
      hitRate: hit,
    });
  }
  return out;
}

/** Return over the last N sessions of the equity curve. */
export function periodReturn(
  eq: readonly EquityCurvePoint[],
  daysBack: number,
): number {
  if (eq.length < 2) return 0;
  const start = Math.max(0, eq.length - 1 - daysBack);
  return eq[eq.length - 1].value / eq[start].value - 1;
}

/** Recovery / underwater statistics. Single pass over equity curve.
 *  - avgRecoveryDays: mean #sessions from local trough back to prior
 *    peak across all completed drawdown episodes
 *  - longestUnderwaterDays: longest stretch where equity < running max
 *  - daysSinceLastHigh: sessions since most recent all-time high
 */
export interface RecoveryStats {
  readonly avgRecoveryDays: number | null;
  readonly longestUnderwaterDays: number;
  readonly daysSinceLastHigh: number;
  readonly nDrawdownEpisodes: number;
}
export function recoveryStats(eq: readonly EquityCurvePoint[]): RecoveryStats {
  if (eq.length === 0) {
    return {
      avgRecoveryDays: null,
      longestUnderwaterDays: 0,
      daysSinceLastHigh: 0,
      nDrawdownEpisodes: 0,
    };
  }
  let peak = eq[0].value;
  let peakIdx = 0;
  let inDD = false;
  let troughIdx = 0;
  let troughVal = peak;
  let underwaterStart = 0;
  let longestUnderwater = 0;
  let lastHighIdx = 0;
  const recoveries: number[] = [];

  for (let i = 1; i < eq.length; i++) {
    const v = eq[i].value;
    if (v >= peak) {
      if (inDD) {
        recoveries.push(i - troughIdx);
        const underwater = i - underwaterStart;
        if (underwater > longestUnderwater) longestUnderwater = underwater;
        inDD = false;
      }
      peak = v;
      peakIdx = i;
      lastHighIdx = i;
      troughVal = v;
      troughIdx = i;
    } else {
      if (!inDD) {
        inDD = true;
        underwaterStart = peakIdx + 1;
        troughVal = v;
        troughIdx = i;
      } else if (v < troughVal) {
        troughVal = v;
        troughIdx = i;
      }
    }
  }
  if (inDD) {
    const underwater = eq.length - underwaterStart;
    if (underwater > longestUnderwater) longestUnderwater = underwater;
  }
  const avg = recoveries.length > 0
    ? recoveries.reduce((a, b) => a + b, 0) / recoveries.length
    : null;
  return {
    avgRecoveryDays: avg,
    longestUnderwaterDays: longestUnderwater,
    daysSinceLastHigh: eq.length - 1 - lastHighIdx,
    nDrawdownEpisodes: recoveries.length + (inDD ? 1 : 0),
  };
}

/** Jaccard similarity between two ticker arrays. */
export function jaccard(
  a: readonly string[],
  b: readonly string[],
): number {
  if (a.length === 0 && b.length === 0) return 0;
  const sa = new Set(a);
  const sb = new Set(b);
  let inter = 0;
  Array.from(sa).forEach((x) => {
    if (sb.has(x)) inter += 1;
  });
  const union = sa.size + sb.size - inter;
  return union === 0 ? 0 : inter / union;
}

export function intersection<T>(
  a: readonly T[],
  b: readonly T[],
): readonly T[] {
  const sb = new Set(b);
  return a.filter((x) => sb.has(x));
}
