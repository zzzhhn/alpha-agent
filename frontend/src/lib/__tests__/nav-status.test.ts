import { describe, expect, it } from "vitest";
import { NAV_GROUPS, isNavActive, navLabels } from "@/lib/nav-items";
import {
  ALERT_BADGE_CAP, alertsSignal, evolutionSignal, picksSignal,
  type AlertAttention, type NavStatusResponse,
} from "@/lib/nav-status";
import { parseSidebarMode } from "@/lib/sidebar-state";

const picks = (state: NavStatusResponse["picks"]["state"], extra: Partial<NavStatusResponse["picks"]> = {}): NavStatusResponse["picks"] => ({
  state, reason: null, market_date: "2026-11-09", expected_market_date: "2026-11-10",
  sessions_behind: 1, next_publish_at: "2026-11-11T23:00:00+00:00", ...extra,
});
const evolution = (state: NavStatusResponse["evolution"]["state"], pending = 0): NavStatusResponse["evolution"] => ({
  state, workflow_state: null, last_run_at: "2026-11-02T16:53:42+00:00", last_run_ok: false, pending_reviews: pending,
});
const attention = (needs: number, critical = 0, source: AlertAttention["source_status"] = "fresh"): AlertAttention => ({
  needs_action: needs, critical, window: 50, newest_at: null, as_of: "2026-11-11T08:00:00Z", source_status: source,
});

describe("bilingual navigation", () => {
  it("covers every requested route with both names", () => {
    const items = NAV_GROUPS.flatMap((group) => group.items);
    expect(items.map((item) => item.href)).toEqual([
      "/picks", "/paper", "/alerts", "/alpha", "/backtest", "/screener", "/report",
      "/factors", "/evolution", "/brain", "/guide", "/data", "/methodology", "/reference", "/settings",
    ]);
    for (const item of items) {
      expect(item.zh).toMatch(/\S/);
      expect(item.en).toMatch(/\S/);
      // Neither name embeds the other locale, which is what caused duplication.
      expect(item.zh.includes(item.en) && item.en !== "BRAIN Mining").toBe(false);
    }
  });
  it("leads with the active locale", () => {
    const item = { zh: "今日推荐", en: "Picks" };
    expect(navLabels(item, "zh")).toEqual({ primary: "今日推荐", secondary: "Picks" });
    expect(navLabels(item, "en")).toEqual({ primary: "Picks", secondary: "今日推荐" });
  });
  it("keeps sub-routes active without matching sibling prefixes", () => {
    expect(isNavActive("/paper/bot", "/paper")).toBe(true);
    expect(isNavActive("/picks", "/picks")).toBe(true);
    expect(isNavActive("/picksx", "/picks")).toBe(false);
    expect(isNavActive(null, "/picks")).toBe(false);
  });
  it("defaults the collapse preference to expanded", () => {
    expect(parseSidebarMode(undefined)).toBe("expanded");
    expect(parseSidebarMode("collapsed")).toBe("collapsed");
    expect(parseSidebarMode("weird")).toBe("expanded");
  });
});

describe("picks freshness signal", () => {
  it("shows nothing for a current snapshot", () => {
    expect(picksSignal(picks("current", { sessions_behind: 0 }), false, "zh")).toBeNull();
  });
  it("treats an unreadable status as unknown, never healthy", () => {
    expect(picksSignal(null, true, "zh")?.tone).toBe("muted");
    expect(picksSignal(picks("current"), true, "en")?.badge).toBe("?");
  });
  it("distinguishes awaiting, delayed, stale and failed", () => {
    expect(picksSignal(picks("awaiting_publish"), false, "zh")?.tone).toBe("info");
    const delayed = picksSignal(picks("delayed"), false, "zh");
    expect(delayed?.tone).toBe("warning");
    expect(delayed?.detail).toContain("2026-11-10");
    expect(delayed?.detail).toContain("2026-11-09");
    expect(picksSignal(picks("stale", { sessions_behind: 3 }), false, "en")?.badge).toBe("3d behind");
    expect(picksSignal(picks("failed", { reason: "run_health_gate_failed" }), false, "en")?.tone).toBe("negative");
  });
});

describe("alerts attention signal", () => {
  it("is hidden when signed out or nothing needs action", () => {
    expect(alertsSignal(null, "signed_out", "zh")).toBeNull();
    expect(alertsSignal(attention(0), "ok", "zh")).toBeNull();
  });
  it("caps the badge but keeps the full count in the description", () => {
    const signal = alertsSignal(attention(140), "ok", "zh");
    expect(signal?.badge).toBe(`${ALERT_BADGE_CAP}+`);
    expect(signal?.detail).toContain("140");
  });
  it("escalates tone only for critical items", () => {
    expect(alertsSignal(attention(3), "ok", "en")?.tone).toBe("attention");
    expect(alertsSignal(attention(3, 1), "ok", "en")?.tone).toBe("negative");
  });
  it("marks unreadable counts and stale sources as muted", () => {
    expect(alertsSignal(null, "error", "en")?.badge).toBe("?");
    expect(alertsSignal(attention(0, 0, "stale"), "ok", "en")?.tone).toBe("muted");
  });
});

describe("evolution signal", () => {
  it("does not present a deliberate pause as a failure", () => {
    const paused = evolutionSignal(evolution("disabled"), false, "zh");
    expect(paused?.tone).toBe("muted");
    expect(paused?.detail).toContain("不是故障");
  });
  it("separates an automatic pause after failure from an active failure", () => {
    expect(evolutionSignal(evolution("paused_after_failure"), false, "en")?.tone).toBe("warning");
    expect(evolutionSignal(evolution("failed"), false, "en")?.tone).toBe("negative");
  });
  it("shows only pending reviews while idle and links to the review queue", () => {
    expect(evolutionSignal(evolution("idle"), false, "en")).toBeNull();
    const review = evolutionSignal(evolution("idle", 4), false, "en");
    expect(review?.badge).toBe("4");
    expect(review?.hash).toBe("evolution-review");
  });
  it("reports unknown scheduler state without claiming failure", () => {
    expect(evolutionSignal(evolution("unknown"), false, "zh")?.detail).toContain("不代表故障");
    expect(evolutionSignal(null, true, "zh")?.badge).toBe("?");
  });
});
