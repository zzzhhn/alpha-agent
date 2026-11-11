import type { EvolutionChange, EvolutionWeight } from "@/lib/api/evolution";
import type { BriefingItem, MiningBriefing } from "@/lib/api/factor-lab";
import type { Locale } from "@/lib/i18n";

// The wire API also returns effective (and may add other statuses).
export type ObservatoryWeight = Omit<EvolutionWeight, "status"> & { status: string };
const WEIGHT_STATUSES = ["live", "effective", "shadow", "guarded_shadow"] as const;
type WeightStatus = typeof WEIGHT_STATUSES[number];
export interface SignalWeightRow {
  signal_name: string;
  live: ObservatoryWeight | null;
  effective: ObservatoryWeight | null;
  shadow: ObservatoryWeight | null;
  guarded_shadow: ObservatoryWeight | null;
  latest: ObservatoryWeight | null;
}

function timestamp(value: string | null): number {
  const parsed = value ? Date.parse(value) : NaN;
  return Number.isFinite(parsed) ? parsed : -Infinity;
}

export function pivotSignalWeights(weights: readonly ObservatoryWeight[]): SignalWeightRow[] {
  const rows = new Map<string, SignalWeightRow>();
  for (const weight of weights) {
    const row = rows.get(weight.signal_name) ?? {
      signal_name: weight.signal_name, live: null, effective: null,
      shadow: null, guarded_shadow: null, latest: null,
    };
    for (const status of WEIGHT_STATUSES) {
      if (weight.status !== status) continue;
      if (!row[status] || timestamp(weight.last_updated) > timestamp(row[status].last_updated)) {
        row[status] = weight;
      }
      if (!row.latest || timestamp(weight.last_updated) > timestamp(row.latest.last_updated)) {
        row.latest = weight;
      }
    }
    rows.set(weight.signal_name, row);
  }
  return [...rows.values()].sort((a, b) =>
    (b.live?.weight ?? -Infinity) - (a.live?.weight ?? -Infinity)
    || a.signal_name.localeCompare(b.signal_name));
}

export function selectFocusSignals(
  weights: readonly ObservatoryWeight[], changes: readonly EvolutionChange[], nowMs: number,
): string[] {
  const recent = new Map<string, number>();
  const cutoff = nowMs - 7 * 24 * 60 * 60 * 1000;
  function record(signal: string | null | undefined, at: string | null) {
    const time = timestamp(at);
    if (signal && time >= cutoff && time <= nowMs) {
      recent.set(signal, Math.max(recent.get(signal) ?? -Infinity, time));
    }
  }
  for (const weight of weights) record(weight.signal_name, weight.last_updated);
  for (const change of changes) {
    let signal = change.signal;
    if (!signal) {
      try {
        const value: unknown = JSON.parse(change.new_value);
        if (value && typeof value === "object" && "signal" in value && typeof value.signal === "string") {
          signal = value.signal;
        }
      } catch { /* Unattributed ledger entries cannot identify a focus signal. */ }
    }
    record(signal, change.changed_at);
  }
  if (recent.size) {
    return [...recent].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, 3).map(([signal]) => signal);
  }
  const rows = pivotSignalWeights(weights);
  const status: WeightStatus = rows.some((row) => row.live) ? "live" : "effective";
  return rows.filter((row) => row[status]).sort((a, b) =>
    b[status]!.weight - a[status]!.weight || a.signal_name.localeCompare(b.signal_name))
    .slice(0, 3).map((row) => row.signal_name);
}

export function formatWeightReason(raw: string | null, locale: Locale = "zh"): string {
  const zh = locale === "zh";
  const text = (raw ?? "").toLowerCase();
  if (text.includes("auto_promote")) return zh ? "自动晋升" : "Auto-promotion";
  if (text.includes("auto_rollback")) return zh ? "自动回滚" : "Auto-rollback";
  if (text.includes("inversion_guard") || text.includes("persistent negative ic")) return zh ? "IC 持续为负，权重清零" : "Persistent negative IC; weight zeroed";
  if (text.includes("ic recovered")) return zh ? "IC 恢复" : "IC recovered";
  try {
    const value: unknown = JSON.parse(raw ?? "");
    if (value && typeof value === "object" && "mode" in value && value.mode === "adaptive_guarded") {
      const alpha = "alpha" in value && typeof value.alpha === "number" ? value.alpha : "—";
      return zh ? `自适应（守护）α=${alpha}` : `Adaptive (guarded) α=${alpha}`;
    }
  } catch { /* Plain-text reasons are also supported. */ }
  if (text.includes("guarded shrinkage")) return zh ? "守护收缩（影子，未上线）" : "Guarded shrinkage (shadow, not live)";
  if (text.includes("cold_start_seed")) return zh ? "冷启动种子" : "Cold-start seed";
  return zh ? "其他" : "Other";
}

export function hasEnoughIcObservations(count: number): boolean {
  return count >= 5;
}

export interface BriefingEntry { item: BriefingItem; flagged: boolean }
export const BRIEFING_PAGE_SIZE = 10;

export function dedupeBriefingItems(briefing: Pick<MiningBriefing, "validated" | "flagged">): BriefingEntry[] {
  const newest = new Map<string, BriefingEntry>();
  // BriefingItem has no timestamp; monotonically increasing proposal IDs
  // identify the newest record. A same-ID tie retains the flagged warning.
  const entries = [
    ...briefing.flagged.map((item) => ({ item, flagged: true })),
    ...briefing.validated.map((item) => ({ item, flagged: false })),
  ];
  for (const entry of entries) {
    const expression = entry.item.expression.replace(/\s+/g, "");
    const previous = newest.get(expression);
    if (!previous || entry.item.id > previous.item.id) newest.set(expression, entry);
  }
  return [...newest.values()].sort((a, b) => b.item.id - a.item.id);
}

export function paginateBriefingItems(entries: readonly BriefingEntry[], page: number): { page: number; items: BriefingEntry[] } {
  const last = Math.max(1, Math.ceil(entries.length / BRIEFING_PAGE_SIZE));
  const current = Number.isFinite(page) ? Math.min(last, Math.max(1, Math.floor(page))) : 1;
  return { page: current, items: entries.slice((current - 1) * BRIEFING_PAGE_SIZE, current * BRIEFING_PAGE_SIZE) };
}
