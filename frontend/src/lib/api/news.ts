// frontend/src/lib/api/news.ts
//
// Read-time BYOK enrichment client. Calls POST /api/news/enrich/{ticker}
// which uses the authenticated user's stored LLM key (no server-side
// global key). 400 = user has not added a key in /settings.
import { apiPost } from "./client";

export interface EnrichResponse {
  ticker: string;
  enriched: number;
  failed_batches: number;
}

/**
 * `lang` controls the language of the per-headline reasoning text the LLM
 * writes into news_items.reasoning_text. Frontend passes the user's
 * active locale ("zh" or "en") so the analyst commentary matches the UI.
 * Defaults to English when omitted (matches the backend default).
 */
export const enrichNewsForTicker = (ticker: string, lang: "zh" | "en" = "en") =>
  apiPost<EnrichResponse, void>(
    `/api/news/enrich/${ticker.toUpperCase()}?lang=${lang}`,
    undefined as unknown as void,
  );
