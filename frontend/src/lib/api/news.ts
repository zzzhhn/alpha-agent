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

export const enrichNewsForTicker = (ticker: string) =>
  apiPost<EnrichResponse, void>(
    `/api/news/enrich/${ticker.toUpperCase()}`,
    undefined as unknown as void,
  );
