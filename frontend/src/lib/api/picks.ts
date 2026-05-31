// frontend/src/lib/api/picks.ts
import { apiGet, apiPost, type ApiGetOptions } from "./client";

export interface BreakdownEntry {
  signal: string;
  // Numeric fields may be null when the backend's NaN sanitizer mapped an
  // unrepresentable IEEE 754 value (NaN/Inf from a degenerate signal) to
  // JSON null. Components must handle null defensively (use `?? 0`).
  z: number | null;
  weight: number | null;
  weight_effective: number | null;
  contribution: number | null;
  raw: unknown;
  source: string;
  timestamp: string;
  error: string | null;
}

export interface NewsItemLite {
  id: number;
  source: string;
  headline: string;
  url: string;
  published_at: string;
  sentiment_score: number | null;
  sentiment_label: "pos" | "neg" | "neu" | null;
  // V007 (2026-05-19): per-headline LLM commentary surfaced beneath the
  // headline so the user gets the *why* (not just the red/green/gray dot).
  // reasoning_lang = the locale the LLM wrote in ("zh"|"en") — used for the
  // <p lang=> attribute, no auto-translation.
  reasoning_text?: string | null;
  reasoning_lang?: string | null;
}

export interface RatingCard {
  ticker: string;
  rating: "BUY" | "OW" | "HOLD" | "UW" | "SELL";
  // Same nullable contract as BreakdownEntry — composite/confidence
  // may arrive as null when DB column held NaN before storage-side fix
  // landed (legacy rows). Components must coalesce.
  confidence: number | null;
  composite_score: number | null;
  as_of: string;
  breakdown: BreakdownEntry[];
  top_drivers: string[];
  top_drags: string[];
  // True for a slow-only row: daily-pipeline data with rating/confidence
  // derived (no fast factors), can be up to ~1 day old. Absent on the
  // single-card /api/stock response, hence optional.
  partial?: boolean;
  // B2 (2026-05-19): true when the hysteresis no-trade band absorbed a
  // tier flip today (raw unbanded mapping differed from the sticky rating
  // the user sees). Surfaced as a small badge for transparency.
  tier_flip_today?: boolean;
  // B5 (2026-05-19): GEX intraday regime classifier. Null when option
  // chain unavailable for this ticker. Surfaced as a header pill so the
  // user disambiguates "buy-the-dip works" (pinned) from "trend
  // continuation" (volatile). Conditioning variable only — not folded
  // into composite_score.
  gex_info?: GexInfo | null;
  // B8 (2026-05-19): per-dimension letter grades (Momentum / Technical /
  // Sentiment / Catalyst / Insider / Flow), each A+ to F derived from
  // breakdown z-scores. Empty dimensions render as "—".
  dimension_grades?: Record<string, string>;
  news_items?: NewsItemLite[];
}

export interface GexInfo {
  regime: "pinned" | "volatile" | "mixed";
  signed_notional: number;
  n_strikes: number;
  dominant_expiry: string;
  spot: number;
}

export type FactorMode = "short" | "long";
// P1-2 two-sided view: "long" = top-N by composite (highest conviction),
// "short" = bottom-N by composite (most bearish UW/SELL names).
export type PicksSide = "long" | "short";

export const fetchPicks = (
  limit = 50,
  search?: string,
  mode: FactorMode = "short",
  side: PicksSide = "long",
  opts?: ApiGetOptions,
) => {
  const params = new URLSearchParams({ limit: String(limit), mode, side });
  const q = search?.trim();
  if (q) params.set("search", q);
  return apiGet<{ picks: RatingCard[]; as_of: string | null; stale: boolean }>(
    `/api/picks/lean?${params.toString()}`,
    opts,
  );
};

export const fetchStock = (ticker: string, opts?: ApiGetOptions) =>
  apiGet<{ card: RatingCard; stale: boolean }>(
    `/api/stock/${ticker.toUpperCase()}`,
    opts,
  );

export interface BriefRequest {
  mode: "lean" | "rich";
  llm_provider?: string;
  api_key?: string;
}

export const postBrief = (ticker: string, body: BriefRequest) =>
  apiPost<
    {
      ticker: string;
      rating: string;
      thesis: { bull: string[]; bear: string[] };
      rendered_at: string;
    },
    BriefRequest
  >(`/api/brief/${ticker.toUpperCase()}`, body);

// frontend/src/lib/api/picks.ts (additions — append after postBrief)

/**
 * Expected shape of `breakdown[signal="factor"].raw` after M4a. Block
 * components cast via `raw as FactorRaw | null`; legacy rows from before
 * the signal enrichment may still have raw=float, so the cast is unsafe —
 * the block must check `typeof raw === "object" && raw !== null` first.
 */
export interface FundamentalsData {
  pe_trailing: number | null;
  pe_forward: number | null;
  eps_ttm: number | null;
  market_cap: number | null;
  dividend_yield: number | null;
  profit_margin: number | null;
  debt_to_equity: number | null;
  beta: number | null;
}

export interface FactorRaw {
  z: number;
  // Phase 2 dual-mode: z_short = 12d/60d (short-window, default), z_long =
  // 252d/126d (academic Jegadeesh-Titman / Daniel-Moskowitz framework).
  // The active mode's value lives in `z`; both alternatives are persisted
  // so the UI toggle can re-display without round-tripping the cron.
  z_short?: number;
  z_long?: number;
  fundamentals: FundamentalsData | null;
}

export interface NewsItem {
  title: string;
  publisher: string;
  published_at: string; // ISO 8601
  link: string;
  sentiment: "pos" | "neg" | "neu";
}

export interface NewsRaw {
  n: number;
  mean_sent: number;
  headlines: NewsItem[];
}

export interface EarningsRaw {
  surprise_pct: number | null;
  days_to_earnings: number | null;
  next_date: string | null; // YYYY-MM-DD
  days_until: number | null;
  eps_estimate: number | null;
  revenue_estimate: number | null;
}

export interface OhlcvBar {
  date: string; // YYYY-MM-DD
  // Backend (yf_helpers.extract_ohlcv post A1 fix) propagates null when
  // yfinance returned NaN/missing prices. Chart consumer (Task E1) must
  // drop or gap-fill the bar.
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number;
}

export interface OhlcvResponse {
  ticker: string;
  period: string;
  bars: OhlcvBar[];
}

export const fetchOhlcv = (
  ticker: string,
  period = "6mo",
  opts?: ApiGetOptions,
) =>
  apiGet<OhlcvResponse>(
    `/api/stock/${ticker.toUpperCase()}/ohlcv?period=${period}`,
    opts,
  );

// Minute-level intraday bars for a single calendar date. Backed by the
// minute_bars rolling 30d cache; `out_of_range=true` means the date is
// outside the retention window and the bars list will be empty.
export interface MinuteBar {
  ts: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number;
}

export interface MinuteBarsResponse {
  ticker: string;
  date: string;
  bars: MinuteBar[];
  out_of_range: boolean;
}

export const fetchMinuteBars = (ticker: string, date: string) =>
  apiGet<MinuteBarsResponse>(
    `/api/stock/${ticker.toUpperCase()}/minute_bars?date=${date}`,
  );


// B4 (2026-05-19) — Event-on-chart + LLM range explanation.

export interface ChartEvent {
  ts: string;
  type: "news" | "macro_political" | "macro_geopolitical";
  headline: string;
  url: string | null;
  sentiment_score: number | null;
  sentiment_label: string | null;
}

export interface ChartEventsResponse {
  ticker: string;
  from_ts: string;
  to_ts: string;
  events: ChartEvent[];
}

export const fetchChartEvents = (
  ticker: string,
  fromTs: string,
  toTs: string,
  opts?: ApiGetOptions,
) =>
  apiGet<ChartEventsResponse>(
    `/api/stock/${ticker.toUpperCase()}/events?from_ts=${fromTs}&to_ts=${toTs}`,
    opts,
  );

export interface ExplainRangeResponse {
  ticker: string;
  from_ts: string;
  to_ts: string;
  explanation: string;
  event_count: number;
  cache: "hit" | "miss";
}

// Company "About" card (yfinance Ticker.info). All fields optional — a
// delisted/obscure ticker may have none, in which case the card hides.
export interface CompanyProfile {
  ticker: string;
  name: string | null;
  // Chinese company name (V019). Null until backfilled; equals `name` when no
  // established Chinese name exists. Show in zh locale; name_zh !== name means
  // a real Chinese name is available.
  name_zh: string | null;
  sector: string | null;
  industry: string | null;
  summary: string | null;
  // Actual language of `summary`. When the UI is in zh but this is "en",
  // the Chinese translation hasn't been backfilled yet — show a note.
  summary_lang: "zh" | "en" | null;
  website: string | null;
  country: string | null;
  employees: number | null;
}

export const fetchProfile = (
  ticker: string,
  lang: "zh" | "en" = "en",
  opts?: ApiGetOptions,
) =>
  apiGet<CompanyProfile>(
    `/api/stock/${ticker.toUpperCase()}/profile?lang=${lang}`,
    opts,
  );

export const explainRange = (
  ticker: string,
  fromTs: string,
  toTs: string,
  language: "zh" | "en",
) =>
  apiPost<ExplainRangeResponse, Record<string, never>>(
    `/api/stock/${ticker.toUpperCase()}/explain_range?from_ts=${fromTs}&to_ts=${toTs}&language=${language}`,
    {},
  );
