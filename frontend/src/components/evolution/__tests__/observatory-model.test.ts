import { describe, expect, it } from "vitest";
import type { EvolutionChange } from "@/lib/api/evolution";
import type { BriefingItem } from "@/lib/api/factor-lab";
import {
  dedupeBriefingItems, formatWeightReason, hasEnoughIcObservations,
  paginateBriefingItems, pivotSignalWeights, selectFocusSignals,
  type ObservatoryWeight,
} from "../observatory-model";

const now = Date.parse("2026-11-11T12:00:00Z");
const recent = "2026-11-10T12:00:00Z";
function weight(signal_name: string, status = "live", value = 0.1, last_updated: string | null = null): ObservatoryWeight {
  return { signal_name, status, weight: value, last_updated, reason: null, consecutive_bad_windows: 0, shadow_streak: 0 };
}
function change(signal: string | null, changed_at = recent, new_value = "{}"): EvolutionChange {
  return { id: 1, source: "auto_promote", signal, changed_at, new_value, rollback_of: null };
}
function item(id: number, expression = `signal_${id}`): BriefingItem {
  return { id, expression, source: null, deflated_sharpe: null, ic_oos: null, self_correlation: 0, risk_level: null, concerns: [] };
}

describe("focus signals", () => {
  it("prefers recent updates over larger live weights, deduplicates and ranks by recency", () => {
    const weights = [weight("large", "live", 0.9), weight("updated", "shadow", 0.01, recent), weight("updated", "live", 0.1, recent)];
    expect(selectFocusSignals(weights, [change("ledger", "2026-11-11T10:00:00Z")], now)).toEqual(["ledger", "updated"]);
  });
  it("parses signal from JSON, tolerates malformed or scalar JSON and uses direct attribution first", () => {
    const changes = [change(null, recent, '{"signal":"parsed"}'), change(null, recent, "broken"), change(null, recent, "null"), change(null, recent, '{"signal":3}'), change("direct", recent, '{"signal":"wrong"}')];
    expect(selectFocusSignals([], changes, now)).toEqual(["direct", "parsed"]);
  });
  it("includes exactly seven days ago and excludes older, invalid and future dates", () => {
    expect(selectFocusSignals([], [
      change("boundary", "2026-11-04T12:00:00Z"), change("old", "2026-11-04T11:59:59Z"),
      change("future", "2026-11-12T12:00:00Z"), change("bad", "invalid"),
    ], now)).toEqual(["boundary"]);
  });
  it("falls back to top three live weights, never shadow or effective when live exists", () => {
    const weights = [weight("a", "live", 0.2), weight("b", "live", 0.4), weight("c", "live", 0.3), weight("d", "live", 0.1), weight("shadow", "shadow", 10), weight("effective", "effective", 20)];
    expect(selectFocusSignals(weights, [], now)).toEqual(["b", "c", "a"]);
    expect(weights[0].signal_name).toBe("a");
  });
  it("falls back to effective only when live rows are absent", () => {
    expect(selectFocusSignals([weight("a", "effective", 0.2), weight("b", "effective", 0.4), weight("shadow", "shadow", 9)], [], now)).toEqual(["b", "a"]);
    expect(selectFocusSignals([], [], now)).toEqual([]);
  });
  it("caps recent results at three and uses deterministic ties", () => {
    expect(selectFocusSignals([], [change("d"), change("c"), change("b"), change("a")], now)).toEqual(["a", "b", "c"]);
  });
});

describe("weight pivot", () => {
  it("keeps all four statuses separate and ignores unknown statuses as column values", () => {
    const rows = pivotSignalWeights([weight("a", "live", 0), weight("a", "effective", 0.2), weight("a", "shadow", 0.3), weight("a", "guarded_shadow", 0.4), weight("a", "retired", 99)]);
    expect(rows).toHaveLength(1);
    expect([rows[0].live?.weight, rows[0].effective?.weight, rows[0].shadow?.weight, rows[0].guarded_shadow?.weight]).toEqual([0, 0.2, 0.3, 0.4]);
  });
  it("keeps the newest status record regardless of input order and exposes newest metadata", () => {
    const newest = { ...weight("a", "shadow", 0.4, recent), reason: "auto_promote" };
    const older = weight("a", "shadow", 0.2, "2026-10-01T00:00:00Z");
    for (const weights of [[newest, older], [older, newest]]) {
      expect(pivotSignalWeights(weights)[0].shadow).toEqual(newest);
      expect(pivotSignalWeights(weights)[0].latest).toEqual(newest);
    }
  });
  it("sorts by live descending, puts missing live last and leaves missing statuses null", () => {
    const rows = pivotSignalWeights([weight("missing", "effective", 100), weight("low", "live", 0), weight("high", "live", 0.8)]);
    expect(rows.map((row) => row.signal_name)).toEqual(["high", "low", "missing"]);
    expect(rows[0].shadow).toBeNull();
    expect(rows[2].live).toBeNull();
  });
});

describe("weight reasons", () => {
  it.each([
    ["auto_promote: x", "自动晋升"], ["auto_rollback", "自动回滚"],
    ["inversion_guard", "IC 持续为负，权重清零"], ["persistent negative IC", "IC 持续为负，权重清零"],
    ["IC recovered", "IC 恢复"], ['{"alpha":0.1,"mode":"adaptive_guarded"}', "自适应（守护）α=0.1"],
    ["council#6 guarded shrinkage (shadow, not live)", "守护收缩（影子，未上线）"],
    ["cold_start_seed", "冷启动种子"], ["unknown", "其他"], ["{broken", "其他"], ["null", "其他"],
  ])("maps %s to %s", (raw, expected) => expect(formatWeightReason(raw)).toBe(expected));
  it("handles missing alpha and provides English copy", () => {
    expect(formatWeightReason('{"mode":"adaptive_guarded"}')).toBe("自适应（守护）α=—");
    expect(formatWeightReason("auto_promote", "en")).toBe("Auto-promotion");
  });
});

describe("IC sample threshold", () => {
  it.each([0, 1, 2, 4])("rejects %i observations as a trend", (count) => expect(hasEnoughIcObservations(count)).toBe(false));
  it.each([5, 6, 100])("allows %i observations", (count) => expect(hasEnoughIcObservations(count)).toBe(true));
});

describe("briefing deduplication and pagination", () => {
  it("normalizes whitespace across both buckets and retains the newest proposal and its bucket", () => {
    const newest = item(9, "rank( close )");
    const result = dedupeBriefingItems({ validated: [item(1, "rank(close)"), item(3, "volume")], flagged: [newest, item(2, "rank(\n close\t)")] });
    expect(result).toEqual([{ item: newest, flagged: true }, { item: item(3, "volume"), flagged: false }]);
  });
  it("retains flagged warning on a same-ID cross-bucket tie", () => {
    expect(dedupeBriefingItems({ validated: [item(1)], flagged: [item(1)] })[0].flagged).toBe(true);
  });
  it("paginates ten unique expressions across buckets and clamps stale pages", () => {
    const result = dedupeBriefingItems({ validated: Array.from({ length: 23 }, (_, i) => item(i + 1)), flagged: [item(30, "signal_1")] });
    expect(result).toHaveLength(23);
    expect(paginateBriefingItems(result, 1).items).toHaveLength(10);
    expect(paginateBriefingItems(result, 2).items).toHaveLength(10);
    expect(paginateBriefingItems(result, 99)).toEqual({ page: 3, items: result.slice(20) });
    expect(paginateBriefingItems(result, 0).page).toBe(1);
    expect(paginateBriefingItems([], 3)).toEqual({ page: 1, items: [] });
  });
});
