// frontend/src/lib/api/factors_library.ts
//
// B7 (2026-05-19) — Alpha158 short-horizon seed library client.
//
// Backend endpoint: GET /api/v1/factors/library?horizon_max=&category=
// Default horizon_max=20 (matches the SHORT factor-mode user); switch
// to 252 to retrieve any future long-horizon seeds when the library
// expands beyond v1's 31-entry subset.
//
// UI integration roadmap:
//   v1 (this commit) — API + TS helper only; user picks from /backtest
//                      by reading the library response and pasting an
//                      expression into the form. Sufficient for the
//                      personal-use phase.
//   v2 (deferred)   — AlphaLibraryGallery component on /factors page
//                      with category filter chips + 1-click "Load into
//                      backtest" CTA, plus the LLM-dedup cosine-sim
//                      check that the synthesizer asked for.

import { apiGet } from "./client";

export interface AlphaSeed {
  name: string;
  expression: string;
  lookback: number;
  category:
    | "momentum"
    | "trend"
    | "volatility"
    | "low_vol"
    | "liquidity"
    | "oscillator"
    | "reversal"
    | "confirmation"
    | "composite";
  description_zh: string;
  description_en: string;
}

export interface AlphaLibraryResponse {
  horizon_max: number;
  category: string | null;
  count: number;
  seeds: AlphaSeed[];
}

export function fetchAlphaLibrary(
  horizonMax: number = 20,
  category?: AlphaSeed["category"],
): Promise<AlphaLibraryResponse> {
  const params = new URLSearchParams({ horizon_max: String(horizonMax) });
  if (category) params.set("category", category);
  return apiGet<AlphaLibraryResponse>(
    `/api/v1/factors/library?${params.toString()}`,
  );
}
