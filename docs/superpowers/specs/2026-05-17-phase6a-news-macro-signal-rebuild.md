# Phase 6a: News + Macro Signal Rebuild (Academic-Grounded)

**Date**: 2026-05-17
**Status**: SPEC (awaiting writing-plans to break into tasks)
**Phase**: 6a (Phase 6b for remaining 8 signals deferred to a separate spec)

---

## Goal

Replace the current LLM-sentiment-scalar-weighted approach in `news` and `macro_events` consumption with an academically-grounded hybrid: LLM-as-Judge discrete tagging + event-study abnormal return measurement, then promote the resulting signals into the picks composite only after a historical IC backtest gate (> 0.02 across 30/60/90 day windows).

## Motivation

The previous design (Phase 5) had `news` signal aggregate LLM `sentiment_score` (a continuous scalar in [-1, 1]) by simple mean, then z-score, then linear-weight into composite. This is a known unreliable pattern in NLP-for-finance literature:

- Tetlock (2007) `Giving Content to Investor Sentiment`: media tone to return is non-linear and state-dependent (recession vs expansion regime IC sign can flip).
- Loughran-McDonald (2011): general LLM sentiment is systematically biased on financial vocabulary (`liability`, `tax`, `amortization` flagged negative when contextually neutral).
- Lopez-Lira-Tang (2023) `Can ChatGPT forecast stock price movements`: same prompt across LLM versions drifts IC by 30%+, undermining reproducibility of scalar score.
- Wagner-Zeckhauser-Ziegler (2018): political event impact (Trump 2016 election) on individual stock returns is bidirectional given identical sentiment polarity, demanding event-study not sentiment-weighting.

The 422 `macro_events` rows backfilled in Phase 5 (407 Truth Social + 15 Fed RSS) currently do not contribute to picks composite at all (no signal module queries the macro_events table). This is a design gap that this spec closes.

## Decisions Locked from Brainstorm (2026-05-17)

| # | Decision | Choice |
|---|---|---|
| 1 | Scope | Phase 6a = news + macro; Phase 6b = remaining 8 signals (separate spec) |
| 2 | Method standard | Each signal must cite >= 1 peer-reviewed paper + pass local IC > 0.02 backtest |
| 3 | Infrastructure | yfinance 1-minute bars (7-30 day rolling), no paid data source in 6a; framework must tolerate fallback to daily-level when minute price unavailable |
| 4 | Publish gate | IC > 0.02 across 30 / 60 / 90 day backtest windows simultaneously, otherwise hold and audit |
| 5 | Macro timing | `political_impact` new signal in P6a same delivery (daily Tetlock-style base + 30-day event-study CAR bonus) |
| 6 | Weight scheme | Dynamic IC-driven monthly walk-forward, IC < 0.02 auto-drops signal weight to 0 |

## Architecture Overview

```
                +-------------------+
                | minute_bars table |  (new)
                | yfinance 1m bars, |
                | 30d rolling SP500 |
                +---------+---------+
                          |
                          v
   +----------------------+----------------------+
   |  event_study.car_calculator                 |  (new module)
   |  60min CAR vs SPY benchmark                 |
   +----------------------+----------------------+
                          |
       +------------------+------------------+
       v                                     v
+------+-------+                    +--------+--------+
| news signal  |                    | political_impact|
| (rewrite)    |                    | (new signal)    |
| - LLM 12-bkt |                    | - 12-bucket LLM |
| - LM dict fb |                    | - macro_events  |
| - daily Tet  |                    |   tickers       |
| - 30d CAR    |                    | - daily Tet     |
| - confidence |                    | - 30d CAR       |
+------+-------+                    +--------+--------+
       |                                     |
       v                                     v
+------+-------------------------------------+------+
|  fusion.combine                                   |
|  (modified to load weights from signal_weight     |
|   _current table, refreshed monthly by IC engine) |
+------+--------------------------------------------+
       |
       v
+------+------+
| picks page  |
| composite + |
| attribution |
+-------------+

Async loop:
  monthly cron -> backtest.ic_engine
                 reads daily_signals_fast + daily_returns
                 computes walk-forward IC per signal x window
                 writes signal_ic_history + updates signal_weight_current
```

## Component 1: Minute-Bar Infrastructure

### Why

Event-study (Brown-Warner 1985) requires intraday price reaction measurement (typical window: 60 minutes post-event). Daily bars lose the ability to attribute a 2 PM Trump tweet to its 60-minute aftermath vs noise from the rest of the day.

### Module

`alpha_agent/data/minute_price.py` (new)

### Responsibilities

- Pull yfinance 1-minute bars for SP500 universe + SPY benchmark, last 7-30 days rolling
- Upsert into `minute_bars` table on conflict (ticker, ts)
- Expose `get_bars_for_event(ticker, event_ts, window_min)` returning DataFrame of (ts, close)
- Sanity check: if event_ts is more than 30 days old, return empty DataFrame (caller must fall back to daily-level path)

### Cron

GHA: every 4 hours during market hours, single shot per ticker shard (similar segmentation pattern to existing `news_per_ticker`)

### Storage

V005 migration:

```sql
CREATE TABLE IF NOT EXISTS minute_bars (
  ticker text NOT NULL,
  ts timestamptz NOT NULL,
  open numeric(12, 4),
  high numeric(12, 4),
  low numeric(12, 4),
  close numeric(12, 4),
  volume bigint,
  fetched_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (ticker, ts)
);
CREATE INDEX IF NOT EXISTS idx_minute_bars_ticker_ts
  ON minute_bars (ticker, ts DESC);
-- 30d rolling cleanup runs via daily slow_daily cron extension
```

### Acceptance

- Pull AAPL last 7 days, row count > 1500 (sanity: 7 days x 390 1-min bars per regular session)
- `get_bars_for_event("AAPL", now() - interval '2 days', 60)` returns 60 rows
- Storage growth: ~500 ticker x 30 days x 390 bars/day = 5.85M rows, ~600 MB; within Neon free tier

## Component 2: CAR (Cumulative Abnormal Return) Calculator

### Why

Standard event-study (MacKinlay 1997): abnormal return = realized return minus expected return. For 60-minute event windows, expected return is approximated by SPY return over the same window (proxy for market factor). Cumulative across the 60 minutes yields the event-attributable price reaction.

### Module

`alpha_agent/event_study/car_calculator.py` (new)

### Function signature

```python
async def compute_car(
    pool: asyncpg.Pool,
    ticker: str,
    event_ts: datetime,
    window_min: int = 60,
) -> CarResult | None:
    """Return CarResult{car_pct, ticker_return, spy_return, n_bars}
    or None if minute bars unavailable for either ticker or SPY in the window."""
```

### Acceptance

- For a synthetic event placed at known good 1-minute window: ticker return = 0.5%, SPY return = 0.2%, CAR = 0.3%
- For an event > 30 days old: returns None (no minute bar coverage)
- For an event in a closed-market hour: returns None (no bars in window)

## Component 3: News Signal Rebuild

### Module

`alpha_agent/signals/news.py` (rewrite, file already exists)

### New methodology

For each `news_items` row in the last 24h for `ticker`:

1. **LLM-as-Judge tagging** (Ke-Kelly-Xiu 2019 style): rather than continuous score, the LLM emits one of 12 discrete buckets:
   - `impact in {none, low, medium, high}` (4 levels)
   - `direction in {bullish, bearish, neutral}` (3 levels)
   - Cross product = 12 discrete labels
   - Cost guard: max 100 rows per user enrich call (already in P5b)

2. **LM dictionary fallback** (Loughran-McDonald 2011): if user has no BYOK key OR enrich budget exhausted, run LM financial dictionary over headline + body, count pos/neg term ratio, map to one of 3 buckets (`bullish / bearish / neutral`) at low confidence
   - Bundled wordlist ships in `alpha_agent/news/lm_dictionary.py` (pos: ~350 terms, neg: ~2300 terms per LM 2011)

3. **Daily aggregation** (Tetlock 2007 style): for each ticker, count rows per (impact, direction) bucket in last 24h, compute weighted Tetlock score:
   - `tetlock_score = sum(rows_in_bucket * impact_weight * direction_sign) / total_rows`
   - `impact_weight: {none: 0, low: 0.3, medium: 0.7, high: 1.0}`
   - `direction_sign: {bullish: +1, bearish: -1, neutral: 0}`
   - Result is in approximately [-1, +1] range

4. **Event-study CAR enrichment** (when minute_bars covers the event): for each high-impact news_item in last 30 days, compute 60-min CAR, store as separate field. Aggregate `mean_high_impact_car_30d` per ticker. This bypasses LLM tagging noise entirely and grounds the signal in actual market reaction.

5. **Final z-score**: combine `tetlock_score` and `mean_high_impact_car_30d` (when available) via simple average, then z-score across SP500 cross-section. Confidence is 0.7 when both signals present, 0.5 when only Tetlock, 0.3 when only LM fallback.

### Acceptance

- AAPL with 5 LLM-tagged news in last 24h (3 bullish-medium, 2 neutral-low): Tetlock score ~ 0.42
- AAPL with no key, fallback to LM dictionary: confidence 0.3, signal still present
- Top 30 SP500 with active news + minute_bars coverage: CAR enrichment runs, signal confidence 0.7

## Component 4: New `political_impact` Signal

### Module

`alpha_agent/signals/political_impact.py` (new)

### Methodology

Mirrors news signal architecture but sources from `macro_events.tickers_extracted` (already populated by Phase 5 LLM enrichment):

1. Query `macro_events WHERE ticker = ANY(tickers_extracted) AND published_at > now() - interval '7 days'` (7d, not 24h, because macro events have longer half-life than ticker-specific news)
2. LLM-as-Judge 12-bucket tagging on event title + body (same prompt schema as news)
3. Tetlock-style aggregation over the 7d window
4. Event-study CAR enrichment when minute_bars covers the event timestamp (most useful for Trump tweets within last 30 days)
5. Final z-score: combine Tetlock + CAR similarly, output `SignalScore` matching existing protocol

### Disambiguation from existing `macro` signal

Existing `macro` signal (VIX / sector ETF / TED spread style) is volatility / risk-regime driven, completely orthogonal to political events. To prevent UI confusion, rename in attribution display:

- existing `macro` signal -> displayed as `Macro (Vol)`
- new `political_impact` signal -> displayed as `Political`

Backend signal name remains `macro` and `political_impact` respectively. Display label is added in frontend AttributionTable + AttributionRadar.

### Acceptance

- TSLA with 3 Trump truths in last 7d mentioning Tesla, LLM tags 2 bullish-high + 1 bearish-medium: Tetlock score ~ 0.5
- AAPL with 0 macro events mentioning it: signal returns `n=0` empty state, confidence 0.3
- Trump truth from 2 days ago at 14:30 UTC mentioning NVDA: CAR enrichment runs, signal confidence 0.7

## Component 5: Dynamic Weight Engine

### Module

`alpha_agent/backtest/ic_engine.py` (new)

### Cron

GHA: monthly on the 1st of each month, 04:00 UTC, single shot calling `POST /api/cron/ic_backtest_monthly`

### Algorithm (walk-forward, lookahead-free)

```
for window_days in [30, 60, 90]:
  for signal_name in active_signals:
    pairs = []
    for as_of in trading_days_in_last_window_days:
      signal_at_as_of = SELECT signal value at as_of (DB only, no lookahead)
      fwd_ret_5d = SELECT (price[as_of + 5d] / price[as_of]) - 1 (must use as_of + 5d not now)
      pairs.append((signal_at_as_of, fwd_ret_5d))
    ic = spearman_rank_corr(pairs)
    write_signal_ic_history(signal_name, window_days, ic, now())

for signal_name in active_signals:
  ics = [ic_30d, ic_60d, ic_90d] from above
  if min(ics) < 0.02:
    weight = 0  # auto-drop
  else:
    weight = mean(ics) * vol_normalize_factor(signal_name)
  upsert_signal_weight_current(signal_name, weight, now())
```

### Storage

V005 (continues from minute_bars migration above):

```sql
CREATE TABLE IF NOT EXISTS signal_ic_history (
  signal_name text NOT NULL,
  window_days integer NOT NULL,
  ic numeric(8, 5) NOT NULL,
  n_observations integer NOT NULL,
  computed_at timestamptz NOT NULL,
  PRIMARY KEY (signal_name, window_days, computed_at)
);
CREATE TABLE IF NOT EXISTS signal_weight_current (
  signal_name text PRIMARY KEY,
  weight numeric(6, 4) NOT NULL,
  last_updated timestamptz NOT NULL,
  reason text  -- 'ic_above_threshold' or 'auto_dropped_low_ic'
);
```

### Acceptance

- After monthly run, `signal_weight_current` has one row per active signal
- A signal with all three window IC < 0.02 has `weight = 0` and `reason = 'auto_dropped_low_ic'`
- `combine.py` reads weights from `signal_weight_current` (not from hardcoded table); auto-dropped signals exit the composite this period

## Component 6: Gating, Monitoring, Observability

### Pre-publish gate (release engineering)

When a new or rewritten signal lands, before it can publish to picks page:

1. Run `ic_engine` backtest in dry-run mode over 30/60/90 day windows
2. All three windows must yield IC > 0.02
3. If pass: insert into `active_signals` whitelist + run live for one cycle, verify no NaN / crash
4. If fail: spec says hold; investigate why (likely a regime mismatch or methodology issue); do not publish even if "looks right"

### Live monitoring

Modify `/api/_health/signals` to additionally return:

```json
{
  "name": "news",
  "live_ic_30d": 0.034,
  "live_ic_60d": 0.041,
  "live_ic_90d": 0.029,
  "weight_current": 0.034,
  "tier": "green"  // green if min > 0.02, yellow if 0.01 < min < 0.02, red if dropped
}
```

### Frontend AttributionTable

Add `live IC` column and tier color dot (green/yellow/red). Auto-dropped signals appear grayed out with `weight = 0` and a `"dropped this cycle"` tooltip.

### Acceptance

- Newly rewritten `news` signal lands and IC dry-run shows 30d=0.04, 60d=0.05, 90d=0.03 -> publishes
- A future regime change pushes news 30d IC to 0.015 in monthly run -> `weight = 0`, signal grayed out in UI, no crash
- `/api/_health/signals` exposes the IC + tier so external monitor can alert

## Deliverables Summary

**New files**:
- `alpha_agent/data/minute_price.py` (yfinance 1m puller)
- `alpha_agent/event_study/car_calculator.py` (60-min CAR vs SPY)
- `alpha_agent/event_study/__init__.py`
- `alpha_agent/news/lm_dictionary.py` (Loughran-McDonald 2011 wordlist bundled)
- `alpha_agent/signals/political_impact.py` (new signal)
- `alpha_agent/backtest/__init__.py`
- `alpha_agent/backtest/ic_engine.py` (walk-forward IC backtest)
- `alpha_agent/api/routes/ic_backtest.py` (POST /api/cron/ic_backtest_monthly handler)
- `alpha_agent/storage/migrations/V005__signal_ic_and_minute_bars.sql`

**Rewritten / modified files**:
- `alpha_agent/signals/news.py` (LLM-as-Judge + LM fallback + CAR enrichment)
- `alpha_agent/fusion/combine.py` (load weights from signal_weight_current, not hardcoded)
- `alpha_agent/api/routes/health.py` (signals endpoint adds IC + tier fields)
- `api/index.py` + `alpha_agent/api/app.py` (dual-entry register ic_backtest router)
- `.github/workflows/cron-shards.yml` (add ic_backtest_monthly cron + minute_bars puller cron)
- `frontend/src/components/stock/AttributionTable.tsx` (add IC column + tier dot)
- `frontend/src/components/stock/AttributionRadar.tsx` (Political vs Macro Vol disambiguate)
- `frontend/src/lib/i18n.ts` (5-8 new keys per locale)

**Deleted nothing in 6a**: existing `macro` signal (VIX style) untouched, just renamed in UI display.

## Academic Reference List

These are the load-bearing citations for the spec; each must appear in the relevant module docstring of the implementing file.

- Tetlock, P. (2007). `Giving Content to Investor Sentiment: The Role of Media in the Stock Market`. Journal of Finance 62(3): 1139-1168. (news signal)
- Loughran, T. & McDonald, B. (2011). `When Is a Liability Not a Liability? Textual Analysis, Dictionaries, and 10-Ks`. Journal of Finance 66(1): 35-65. (LM dictionary fallback)
- Brown, S. & Warner, J. (1985). `Using Daily Stock Returns: The Case of Event Studies`. Journal of Financial Economics 14(1): 3-31. (event-study methodology)
- MacKinlay, A. (1997). `Event Studies in Economics and Finance`. Journal of Economic Literature 35(1): 13-39. (event-study survey)
- Ke, Z., Kelly, B., & Xiu, D. (2019). `Predicting Returns with Text Data`. NBER WP 26186. (LLM-as-Judge frame, discrete bucket motivation)
- Lopez-Lira, A. & Tang, Y. (2023). `Can ChatGPT Forecast Stock Price Movements? Return Predictability and Large Language Models`. arXiv:2304.07619. (LLM bias warning, motivates LM fallback)
- Wagner, A., Zeckhauser, R., & Ziegler, A. (2018). `Company Stock Price Reactions to the 2016 Election Shock`. Journal of Financial Economics 130(2): 428-451. (political-event-study precedent)

## Known Risks and Mitigation

| Risk | Likelihood | Mitigation |
|---|---|---|
| yfinance 1m bars only 7-30 days back, so most of the 422 macro_events backfilled cannot be event-studied | High | Framework explicitly falls back to daily-level Tetlock aggregation for events older than 30 days; minute-bar enrichment is a bonus, not a hard requirement |
| Monthly IC backtest introduces lookahead bias if windows touch future returns | Medium | Strict walk-forward: signal observed at `as_of`, return computed as `as_of + 5d` close, never include any data after the as_of point in either side of the IC calculation |
| `political_impact` and existing `macro` signal confuse users | Medium | UI rename: existing -> `Macro (Vol)`, new -> `Political`; backend names retained |
| LM dictionary fallback may have systematically lower IC than LLM-as-Judge -> auto-dropped even when LLM path would have worked | Medium | Track signal IC by source (LLM vs LM) in `signal_ic_history` separately; if LM-only IC < 0.02 but LLM path IC > 0.02, treat as user-key-uptake problem not signal-dead |
| Monthly cron failure on the 1st means stale weights for 30 days | Low | GHA workflow_dispatch lets us manually retrigger; live monitor on `/api/_health/signals` will surface stale `last_updated` field; alert if last_updated > 35d old |
| `political_impact` signal IC may be sector-specific (e.g., only meaningful for tariff-sensitive stocks) | Medium | Phase 6b backlog item: introduce sector-conditional weights; for 6a, accept the global IC as the gate |

## Phase 6b Backlog (out of scope)

Remaining 8 signals to audit + potentially rebuild using the same framework:

- `factor` (already on Fama-French / q-factor backing, likely passes audit with minor changes)
- `technicals` (Jegadeesh-Titman momentum likely OK; RSI / MACD likely fail audit)
- `analyst` (Ramnath 2008 revision premium; methodology audit)
- `earnings` (Bernard-Thomas 1989 PEAD; verify SUE methodology)
- `insider` (Cohen-Malloy-Pomorski 2012; verify routine vs opportunistic split)
- `options` (Bali-Hovakimian IV-RV spread; audit)
- `premarket` (weak signal, audit may end in removal)
- `macro` Vol (French-Schwert-Stambaugh 1987 VRP; audit)
- `calendar` (Heston-Sadka 2008 seasonality; audit, likely keep as low-weight)

Each gets a separate `2026-XX-XX-phase6b-<signal>-audit.md` spec only if the audit shows methodology issues.

## Effort Estimate

| Stage | Hours | Sessions |
|---|---|---|
| writing-plans (decompose spec into tasks) | 1.5-2 | 1 |
| C1 Infrastructure: minute_bars puller + CAR calc | 2-3 | 1 |
| C3 News signal rewrite + LM dictionary fallback | 2-3 | 1 |
| C4 political_impact signal + macro disambiguate | 1.5-2 | 0.5 |
| C5 IC engine + dynamic weight loading | 3-4 | 1 |
| C6 Gating + observability + UI surface | 1.5-2 | 0.5 |
| Acceptance: 30 / 60 / 90d IC dry-run on rewritten signals, monthly cron deploy | 1.5-2 | 0.5 |
| **Total Phase 6a** | **13-18 hours** | **4-5 sessions** |

## Open Questions for writing-plans Stage

These are not blockers for spec completeness, but should be answered when decomposing into tasks:

1. LLM-as-Judge prompt schema: exact JSON output format (single-message vs multi-turn), token budget per news item batch
2. `vol_normalize_factor(signal_name)` in weight engine: use rolling 90d stdev of signal value, or fixed per-signal scaling constant
3. SP500 universe definition for minute_bars puller: hardcoded list, query daily_signals_slow distinct tickers, or join with watchlist
4. Frontend `tier` color: green/yellow/red mapping to existing tm-pos/tm-warn/tm-neg tokens or new tokens
5. Monthly cron timing: 1st of month 04:00 UTC, or first weekday 14:00 UTC (right before market open) to allow same-day re-weight before live trading window

## Acceptance for Phase 6a Overall (end-to-end)

1. `/api/_health/signals` returns 10 entries with live IC fields populated
2. `news` and `political_impact` both show `tier: green` after publish gate
3. Stock detail page AttributionTable shows live IC column and `Political` row distinct from `Macro (Vol)` row
4. Trump tweet from yesterday mentioning TSLA results in TSLA composite score moving by at least 0.05 (vs same composite without political_impact)
5. Monthly cron executes successfully on 2026-06-01 04:00 UTC; `signal_weight_current` table has fresh rows
6. A staged regime test: simulate news IC dropping to 0.01 by perturbing test data; weight engine auto-drops weight to 0; no crash in fusion or picks endpoint
