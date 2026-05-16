// frontend/src/lib/api/macro.ts
import { apiGet } from "./client";

export interface MacroContextItem {
  id: number;
  author: string | null;
  title: string;
  url: string | null;
  body_excerpt: string | null;
  published_at: string;
  sentiment_score: number | null;
  tickers_extracted: string[];
  sectors_extracted: string[];
}

export const fetchMacroContext = (ticker: string, limit = 5) =>
  apiGet<{ items: MacroContextItem[] }>(
    `/api/macro_context?ticker=${encodeURIComponent(ticker)}&limit=${limit}`,
  );
