import type { FactorMode, PicksResponse, PicksSide, RatingCard } from "@/lib/api/picks";
import { isPicksSnapshotStale } from "@/lib/picks-freshness";

export const RECOMMENDATION_BOARD_SIZE = 50;
export const PAPER_SHORTLIST_SIZE = 5;

export interface PickOrderSource {
  readonly ticker: string;
  readonly mode: FactorMode;
  readonly side: PicksSide;
  readonly runId: number;
  readonly marketDate: string;
}

interface PaperPickQuery {
  readonly ticker: string | null;
  readonly mode: FactorMode;
  readonly side: PicksSide;
  readonly source: PickOrderSource | null;
  readonly invalid: boolean;
}

export function hasSessionClose(card: RatingCard): boolean {
  return !!card.market_date && card.price_date === card.market_date
    && typeof card.latest_price === "number" && Number.isFinite(card.latest_price) && card.latest_price > 0;
}

export function pickOrderSource(card: RatingCard, side: PicksSide): PickOrderSource | null {
  if (!card.run_id || !card.market_date || !card.sleeve || !hasSessionClose(card)) return null;
  return {
    ticker: card.ticker,
    mode: card.sleeve === "strategic" ? "long" : "short",
    side,
    runId: card.run_id,
    marketDate: card.market_date,
  };
}

export function paperOrderHref(source: PickOrderSource): string {
  return `/paper?${new URLSearchParams({
    ticker: source.ticker, mode: source.mode, side: source.side,
    run: String(source.runId), date: source.marketDate,
  })}`;
}

export function readPaperPickQuery(
  params: Pick<URLSearchParams, "get">,
  preferredMode: FactorMode,
): PaperPickQuery {
  const ticker = params.get("ticker")?.trim().toUpperCase() || null;
  const rawMode = params.get("mode");
  const rawSide = params.get("side");
  const rawRun = params.get("run");
  const marketDate = params.get("date");
  const mode = rawMode === "long" || rawMode === "short" ? rawMode : preferredMode;
  const side: PicksSide = rawSide === "short" ? "short" : "long";
  const pinned = rawRun !== null || marketDate !== null;
  const runId = rawRun && /^[1-9]\d*$/.test(rawRun) ? Number(rawRun) : 0;
  const invalidMode = rawMode !== null && rawMode !== mode;
  const invalidSide = rawSide !== null && rawSide !== side;
  const source = pinned && ticker && rawMode && marketDate && /^\d{4}-\d{2}-\d{2}$/.test(marketDate)
    && runId > 0 && Number.isSafeInteger(runId)
    ? { ticker, mode, side, runId, marketDate }
    : null;
  return { ticker, mode, side, source, invalid: invalidMode || invalidSide || (pinned && !source) };
}

export function resolvePaperPick(
  snapshot: PicksResponse,
  query: PaperPickQuery,
  selection: string | null | undefined,
) {
  const { source, mode } = query;
  const run = snapshot.run;
  if (query.invalid && selection === undefined) return { status: "invalid" } as const;
  const sleeve = mode === "long" ? "strategic" : "tactical";
  if (!snapshot.canonical || !snapshot.ranked || run?.sleeve !== sleeve) {
    return { status: "mode_unavailable" } as const;
  }
  if (selection === undefined && source
    && (source.runId !== run.run_id || source.marketDate !== run.market_date)) {
    return { status: "superseded" } as const;
  }
  if (!snapshot.tradable || isPicksSnapshotStale(snapshot.as_of, snapshot.stale)) {
    return { status: "frozen" } as const;
  }

  const ticker = selection === undefined ? query.ticker : selection;
  const matchesRun = (card: RatingCard) => card.run_id === run.run_id
    && card.market_date === run.market_date && card.sleeve === sleeve;
  const pick = ticker
    ? snapshot.picks.find(card => card.ticker === ticker && matchesRun(card))
    : selection === undefined
      ? snapshot.picks.slice(0, PAPER_SHORTLIST_SIZE).find(card => matchesRun(card) && hasSessionClose(card))
      : undefined;
  if (!pick) return { status: ticker ? "not_ranked" : "unselected" } as const;
  if (!hasSessionClose(pick)) return { status: "no_close" } as const;
  return { status: "ready", pick } as const;
}
