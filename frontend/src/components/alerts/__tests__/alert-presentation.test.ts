import { describe, expect, it } from "vitest";

import type { AlertInboxItem } from "@/lib/api/alertsFeed";
import {
  changeSummary,
  evidenceRows,
  queueFor,
  relevanceLabel,
  selectedAlert,
  confidenceLabel,
  workflowLabel,
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
  it("never keeps a hidden alert selected after filtering or paging", () => {
    expect(selectedAlert([], 1)).toBeNull();
    expect(selectedAlert([alert({id:6})], 1)?.id).toBe(6);
    expect(selectedAlert([alert({id:6}),alert({id:7})], 7)?.id).toBe(7);
  });

  it("localizes confidence, workflow and known evidence without inventing values", () => {
    expect(confidenceLabel("low","zh")).toBe("低");
    expect(workflowLabel("open","zh")).toBe("待处理");
    expect(evidenceRows(alert({payload:{n_24h:39,unknown_field:"raw"}}),"zh")).toEqual([["24 小时新闻数","39"],["unknown_field","raw"]]);
  });

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
