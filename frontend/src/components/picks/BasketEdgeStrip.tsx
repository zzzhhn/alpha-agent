"use client";

// Compact "BASKET.EDGE" strip pinned above the picks table. The headline of
// this whole product is "is 今日推荐 meaningful" — and the honest answer is that
// the value is the RANKED long-short BASKET, not any single ticker's 5d
// direction (which is ~coin-flip). This strip surfaces, per horizon, the
// beta-neutral long-short quintile spread (the headline number) and the
// rank-IC, fetched from GET /api/picks/edge.
//
// Honesty: horizons whose forward window has no observable exits yet (the
// fast-signal history is short) come back `insufficient`; we render a muted
// "—" / "数据不足" rather than fabricating an edge.
import { useEffect, useState } from "react";

import {
  fetchBasketEdge,
  type BasketEdgeResponse,
  type HorizonEdge,
} from "@/lib/api/basket_edge";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { HoverTip } from "@/components/ui/HoverTip";

function fmtPct(v: number | null): string {
  if (v === null) return "—";
  const pct = v * 100;
  return `${pct >= 0 ? "+" : ""}${pct.toFixed(2)}%`;
}

function fmtIc(v: number | null): string {
  if (v === null) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(3)}`;
}

function spreadToneClass(v: number | null): string {
  if (v === null) return "text-tm-muted";
  if (v > 0) return "text-tm-pos";
  if (v < 0) return "text-tm-neg";
  return "text-tm-fg";
}

function HorizonCell({ h }: { h: HorizonEdge }) {
  const { locale } = useLocale();
  const insufficientLabel = t(locale, "edge.insufficient");
  return (
    <div className="flex min-w-[88px] flex-col gap-0.5">
      <span className="font-tm-mono text-[11px] uppercase tracking-wide text-tm-muted">
        {h.horizon}d
      </span>
      {h.insufficient ? (
        <span className="font-tm-mono text-[11px] text-tm-muted">
          {insufficientLabel}
        </span>
      ) : (
        <>
          <span
            className={`font-tm-mono text-[13px] font-semibold tabular-nums ${spreadToneClass(
              h.long_short_spread,
            )}`}
          >
            {fmtPct(h.long_short_spread)}
          </span>
          <span className="font-tm-mono text-[11px] tabular-nums text-tm-muted">
            {t(locale, "edge.ic_label")} {fmtIc(h.mean_ic)}
          </span>
        </>
      )}
    </div>
  );
}

export default function BasketEdgeStrip() {
  const { locale } = useLocale();
  const [data, setData] = useState<BasketEdgeResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  // Client-side fetch with a cancelled-effect guard so a fast unmount /
  // re-render never sets state on a stale response.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setFailed(false);
    fetchBasketEdge()
      .then((res) => {
        if (cancelled) return;
        setData(res);
      })
      .catch(() => {
        if (cancelled) return;
        // Degrade gracefully: a missing edge strip must never break the page.
        setFailed(true);
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Hard failure: hide the strip entirely (the picks table is the page; the
  // strip is supplementary).
  if (failed) return null;

  const title = t(locale, "edge.title");
  const spreadLabel = t(locale, "edge.spread_label");

  return (
    <div className="mx-4 mt-3 flex flex-wrap items-center gap-x-6 gap-y-2 rounded border border-tm-rule bg-tm-bg-2 px-3 py-2">
      <div className="flex items-center gap-1.5">
        <span className="font-tm-mono text-[11px] font-semibold uppercase tracking-wider text-tm-accent">
          {title}
        </span>
        <HoverTip content={t(locale, "edge.tip")} placement="bottom" width={272}>
          <span
            className="flex h-3.5 w-3.5 cursor-help items-center justify-center rounded-full border border-tm-rule font-tm-mono text-[9px] leading-none text-tm-muted"
            aria-hidden="true"
          >
            i
          </span>
        </HoverTip>
        <span className="font-tm-mono text-[11px] text-tm-muted">
          {spreadLabel}
        </span>
      </div>

      {loading || !data ? (
        // Muted skeleton while the transpacific query resolves.
        <div className="flex gap-6" aria-hidden="true">
          {[5, 20, 60].map((h) => (
            <div key={h} className="flex min-w-[88px] flex-col gap-0.5">
              <span className="font-tm-mono text-[11px] uppercase tracking-wide text-tm-muted">
                {h}d
              </span>
              <span className="font-tm-mono text-[11px] text-tm-muted">
                {t(locale, "edge.loading")}
              </span>
            </div>
          ))}
        </div>
      ) : (
        <div className="flex flex-wrap gap-x-6 gap-y-2">
          {data.horizons.map((h) => (
            <HorizonCell key={h.horizon} h={h} />
          ))}
        </div>
      )}
    </div>
  );
}
