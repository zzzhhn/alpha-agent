import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AlertGroupReadWindow } from "../AlertGroupReadWindow";
import {
  appendAlertInboxPage,
  applyInboxAlertState,
  fetchAlertInbox,
  type AlertInboxItem,
  type AlertInboxResponse,
  type AlertTriageState,
} from "@/lib/api/alertsFeed";
import { apiGet, apiPost } from "@/lib/api/client";

vi.mock("@/lib/api/client", () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
}));

const open: AlertTriageState = {
  status: "open", snooze_until: null, resolved_at: null, note: null, updated_at: null,
};
const resolved: AlertTriageState = { ...open, status: "resolved" };

function group(overrides: Partial<AlertInboxItem> = {}): AlertInboxItem {
  return {
    id: 51, ticker: "AAPL", type: "rating_change", payload: null, dedup_bucket: 51,
    created_at: "2026-11-11T05:15:00Z", first_seen_at: "2026-11-11T05:01:00Z",
    last_seen_at: "2026-11-11T05:15:00Z", member_ids: [51, 1], occurrences: 2,
    group_id: "AAPL-rating-2026-11-11", group_token: "read-window",
    severity: "critical", relevance: "position", triage_score: 90, freshness_score: 80,
    confidence_score: 80, confidence: "high", source_count: 3, stale: false,
    context: {
      in_position: true, in_recommendation: false, in_watchlist: false,
      recommendation_rank: null, recommendation_run_id: null, recommendation_market_date: null,
    },
    state: open,
    ...overrides,
  };
}

afterEach(() => vi.resetAllMocks());

describe("alert group windows", () => {
  it("renders both timestamps and the number of members covered by actions", () => {
    const html = renderToStaticMarkup(
      <AlertGroupReadWindow item={group()} locale="zh" formatTime={iso => iso.slice(11, 16)} />,
    );
    expect(html).toContain('dateTime="2026-11-11T05:01:00Z">05:01');
    expect(html).toContain('dateTime="2026-11-11T05:15:00Z">05:15');
    expect(html).toContain("处理和撤销只覆盖本次读取的 2 条");
  });

  it("uses the same observed group credential for the undo even after refresh", async () => {
    const item = group({ member_ids: Array.from({ length: 201 }, (_, index) => index + 1) });
    vi.mocked(apiPost)
      .mockResolvedValueOnce({ state: resolved, updated: 201, undo_token: "original-receipt" })
      .mockResolvedValueOnce({ state: open, updated: 201, undo_token: null });
    const receipt = await applyInboxAlertState(item, { status: "resolved", snooze_until: null });
    item.group_token = "refreshed-window";
    item.member_ids?.push(999);
    expect(receipt.updated).toBe(201);
    expect(await receipt.undo?.()).toEqual(open);
    expect(apiPost).toHaveBeenNthCalledWith(1, "/api/alerts/state/group", {
      group_token: "read-window", status: "resolved", snooze_until: null,
    });
    expect(apiPost).toHaveBeenNthCalledWith(2, "/api/alerts/state/group/undo", {
      group_token: "read-window", undo_token: "original-receipt",
    });
  });

  it("keeps sending explicit ids when an older server returns no group credential", async () => {
    vi.mocked(apiPost).mockResolvedValueOnce({ updated: 2, states: { 51: resolved } });
    expect((await applyInboxAlertState(group({ group_token: undefined }), { status: "resolved" })).state).toEqual(resolved);
    expect(apiPost).toHaveBeenCalledWith("/api/alerts/state/batch", { alert_ids: [51, 1], status: "resolved" });
  });

  it("requests the next group page and keeps separate New York dates for the same ticker", async () => {
    const current: AlertInboxResponse = {
      alerts: [group()], counts: { needs_action: 1, watch: 0, record: 0, resolved: 0 },
      as_of: "2026-11-11T06:00:00Z", source_status: "fresh", next_offset: 50,
    };
    const oldDay = group({
      id: 2, group_id: "AAPL-rating-2026-11-10", group_token: "prior-day-window",
      created_at: "2026-11-11T04:59:00Z", first_seen_at: "2026-11-11T04:59:00Z",
      last_seen_at: "2026-11-11T04:59:00Z", occurrences: 1, member_ids: [2],
    });
    const olderPage = { ...current, next_offset: null, alerts: [
      group({ id: 52, group_token: "duplicate-from-live-page" }), oldDay,
    ] };
    vi.mocked(apiGet).mockResolvedValue(olderPage);
    const page = await fetchAlertInbox(50, current.next_offset ?? 0);
    expect(apiGet).toHaveBeenCalledWith("/api/alerts/inbox?limit=50&offset=50");
    const merged = appendAlertInboxPage(current, page);
    expect(merged.alerts.map(item => item.group_token)).toEqual(["read-window", "prior-day-window"]);
    expect(merged.next_offset).toBeNull();
  });
});
