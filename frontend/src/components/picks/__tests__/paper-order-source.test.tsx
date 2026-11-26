import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { PicksResponse, RatingCard } from "@/lib/api/picks";
import PicksCards from "../PicksCards";
import {
  paperOrderHref, pickOrderSource, readPaperPickQuery, resolvePaperPick,
} from "../paper-order-source";

const marketDate = "2026-11-25";
const snapshot: PicksResponse = {
  as_of: `${marketDate}T22:00:00Z`,
  stale: false, canonical: true, ranked: true, tradable: true, changes: null,
  run: {
    run_id: 21, market_date: marketDate, generated_at: null, data_cutoff: null,
    sleeve: "strategic", horizon_days: 60, validation_status: "forward_validation",
    policy_id: "strategic-test", coverage: 1, health: {},
  },
  picks: Array.from({ length: 50 }, (_, i): RatingCard => ({
    ticker: `T${i + 1}`, rating: "OW", composite_score: 50 - i, confidence: 0.5,
    as_of: marketDate, run_id: 21, market_date: marketDate, sleeve: "strategic",
    price_date: marketDate, latest_price: 100, breakdown: [], top_drivers: [], top_drags: [],
  })),
};

function readLink(href: string) {
  return readPaperPickQuery(new URL(href, "http://localhost").searchParams, "short");
}

describe("recommendation-to-paper source", () => {
  it.each([1, 6, 50])("opens rank %i in the linked sleeve and side", (rank) => {
    const card = snapshot.picks[rank - 1];
    const source = pickOrderSource(card, "short");
    expect(source).not.toBeNull();
    const href = paperOrderHref(source!);
    expect(readLink(href)).toMatchObject({ source, mode: "long", side: "short", invalid: false });
    expect(resolvePaperPick(snapshot, readLink(href), undefined)).toEqual({ status: "ready", pick: card });

    const html = renderToStaticMarkup(
      <PicksCards picks={[card]} ranked side="short" ordersDisabled={false} onEvidenceOpen={() => {}} />,
    );
    expect(html).toContain(href.replaceAll("&", "&amp;"));
  });

  it("keeps legacy ticker-only links on the user's current board", () => {
    const query = readPaperPickQuery(new URLSearchParams("ticker=t50"), "long");
    expect(query).toMatchObject({ ticker: "T50", mode: "long", side: "long", invalid: false });
    expect(resolvePaperPick(snapshot, query, undefined).status).toBe("ready");
  });

  it("rejects mismatched provenance, unranked tickers and missing closes", () => {
    const href = paperOrderHref(pickOrderSource(snapshot.picks[5], "short")!);
    const resolve = (state: PicksResponse, link = href) => resolvePaperPick(state, readLink(link), undefined).status;
    expect(resolve(snapshot, href.replace("run=21", "run=20"))).toBe("superseded");
    expect(resolve(snapshot, href.replace("2026-11-25", "2026-11-24"))).toBe("superseded");
    expect(resolve(snapshot, href.replace("mode=long", "mode=short"))).toBe("mode_unavailable");
    expect(resolve(snapshot, href.replace("mode=long", "mode=other"))).toBe("invalid");
    expect(resolve(snapshot, href.replace("&run=21", ""))).toBe("invalid");
    expect(resolve({ ...snapshot, picks: snapshot.picks.slice(0, 5) })).toBe("not_ranked");
    expect(resolve({ ...snapshot, stale: true, tradable: false })).toBe("frozen");
    const noClose = { ...snapshot.picks[5], latest_price: null };
    expect(pickOrderSource(noClose, "short")).toBeNull();
    expect(resolve({ ...snapshot, picks: [noClose] })).toBe("no_close");
  });
});
