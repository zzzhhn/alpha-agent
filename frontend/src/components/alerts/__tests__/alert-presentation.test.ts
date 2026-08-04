import { describe, expect, it } from "vitest";

import type { AlertInboxItem } from "@/lib/api/alertsFeed";
import {
  changeSummary,
  evidenceRows,
  queueFor,
  relevanceLabel,
} from "../alertPresentation";

function alert(overrides: Partial<AlertInboxItem> = {}): AlertInboxItem {
  return {
    id: 1,
    ticker: "AAPL",
    type: "score_spike",
    payload: { delta: 0.45, nested: { ignored: true } },
    dedup_bucket: 1,
    created_at: "2026-08-03T12:00:00Z",
    severity: "warning",
    relevance: "recommendation",
    triage_score: 51,
    freshness_score: 20,
    confidence_score: 10,
    confidence: "medium",
    source_count: 2,
    stale: false,
    context: {
      in_position: false,
      in_recommendation: true,
      in_watchlist: false,
      recommendation_rank: 4,
      recommendation_run_id: 88,
      recommendation_market_date: "2026-08-03",
    },
    state: {
      status: "open",
      snooze_until: null,
      resolved_at: null,
      note: null,
      updated_at: null,
    },
    ...overrides,
  };
}

describe("alert presentation", () => {
  it("routes ranked alerts into decision queues", () => {
    expect(queueFor(alert())).toBe("needs_action");
    expect(queueFor(alert({ triage_score: 30 }))).toBe("watch");
    expect(queueFor(alert({ triage_score: 10 }))).toBe("record");
    expect(queueFor(alert({ state: { ...alert().state, status: "snoozed" } }))).toBe("watch");
    expect(queueFor(alert({ state: { ...alert().state, status: "resolved" } }))).toBe("resolved");
  });

  it("explains structured changes without causal speculation", () => {
    expect(changeSummary(alert(), "en")).toBe("Composite score moved +0.45");
    expect(changeSummary(alert(), "zh")).toContain("+0.45");
  });

  it("only exposes scalar evidence rows", () => {
    expect(evidenceRows(alert())).toEqual([["delta", "0.45"]]);
  });

  it("labels the unlinked record-only relevance filter", () => {
    expect(relevanceLabel("record", "zh")).toBe("仅记录");
    expect(relevanceLabel("record", "en")).toBe("Record only");
  });
});
