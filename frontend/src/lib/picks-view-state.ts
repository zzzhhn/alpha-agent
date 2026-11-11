import type { FactorMode, PicksResponse, PicksSide } from "@/lib/api/picks";
export const PICKS_VIEW_KEY = "alpha:picks_return_v1";
export interface PicksViewState {
  version: 1; ticker: string; search: string; mode: FactorMode; side: PicksSide;
  page: number; pageSize: number; scroll: number; tableScroll: number; data: PicksResponse;
}
export function parsePicksView(raw: string | null): PicksViewState | null {
  try {
    const v = JSON.parse(raw ?? "null");
    if (!v || v.version !== 1 || typeof v.ticker !== "string" || typeof v.search !== "string"
      || !["short", "long"].includes(v.mode) || !["short", "long"].includes(v.side)
      || !Number.isInteger(v.page) || v.page < 1 || ![10, 25, 50].includes(v.pageSize)
      || !Number.isFinite(v.scroll) || !Number.isFinite(v.tableScroll)
      || !Array.isArray(v.data?.picks)) return null;
    return v;
  } catch { return null; }
}
export function loadPicksView(): PicksViewState | null {
  try { return parsePicksView(sessionStorage.getItem(PICKS_VIEW_KEY)); } catch { return null; }
}
export function storePicksView(value: PicksViewState) {
  try { sessionStorage.setItem(PICKS_VIEW_KEY, JSON.stringify(value)); } catch { /* browsing remains available */ }
}
export function clearPicksView() {
  try { sessionStorage.removeItem(PICKS_VIEW_KEY); } catch { /* storage may be disabled */ }
}
