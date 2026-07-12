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

import { Wallet } from "lucide-react";
import {
  fetchBasketEdge,
  fetchPicksScoreboard,
  type BasketEdgeResponse,
  type HorizonEdge,
  type PicksScoreboard,
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

// Realized portfolio scoreboard segment: "had you followed the daily top-K,
// here is the compounded result vs the market average + the blind-guess base
// rate". This is the honest headline the per-name next-day hit-rate can't be.
function ScoreboardCells({ sb }: { sb: PicksScoreboard }) {
  const { locale } = useLocale();
  const items: Array<{ label: string; value: string; tone: string }> = [
    {
      label: t(locale, "edge.sb_long").replace("{n}", String(sb.top_n)),
      value: fmtPct(sb.long_cum),
      tone: spreadToneClass(sb.long_cum),
    },
    {
      label: t(locale, "edge.sb_market"),
      value: fmtPct(sb.market_cum),
      tone: "text-tm-fg-2",
    },
    {
      label: t(locale, "edge.sb_spread"),
      value: fmtPct(sb.spread_cum),
      tone: spreadToneClass(sb.spread_cum),
    },
  ];
  if (sb.long_hit_rate !== null && sb.base_rate !== null) {
    const beats = sb.long_hit_rate > sb.base_rate;
    items.push({
      label: t(locale, "edge.sb_hit"),
      value: `${Math.round(sb.long_hit_rate * 100)}% (${t(locale, "edge.sb_base")} ${Math.round(sb.base_rate * 100)}%)`,
      tone: beats ? "text-tm-pos" : "text-tm-neg",
    });
  }
  return (
    <HoverTip
      content={t(locale, "edge.sb_tip").replace("{d}", String(sb.days))}
      placement="bottom"
      width={272}
    >
      <div className="flex cursor-help flex-wrap items-center gap-x-4 gap-y-1 border-l border-tm-rule pl-4">
        <span className="font-tm-mono text-[11px] uppercase tracking-wide text-tm-muted">
          {t(locale, "edge.sb_title").replace("{d}", String(sb.days))}
        </span>
        {items.map((it) => (
          <span key={it.label} className="flex items-baseline gap-1">
            <span className="font-tm-mono text-[10px] text-tm-muted">{it.label}</span>
            <span className={`font-tm-mono text-[12px] font-semibold tabular-nums ${it.tone}`}>
              {it.value}
            </span>
          </span>
        ))}
      </div>
    </HoverTip>
  );
}

// 2026-07-12: Compact honest metrics block — cost/turnover/SPY/significance.
// Display-only: these numbers measure the ranking, they do not affect it.
function HonestMetricsBlock({
  sb,
  h5,
}: {
  sb: PicksScoreboard;
  h5: import("@/lib/api/basket_edge").HorizonEdge | undefined;
}) {
  const { locale } = useLocale();
  const netPct =
    sb.long_net_cum !== null ? fmtPct(sb.long_net_cum) : "—";
  const spyPct = sb.spy_cum !== null ? fmtPct(sb.spy_cum) : "—";
  const toStr =
    sb.mean_daily_turnover !== null
      ? `${(sb.mean_daily_turnover * 100).toFixed(1)}%`
      : "—";
  const beStr =
    sb.breakeven_cost_bps !== null
      ? `${sb.breakeven_cost_bps.toFixed(0)} bps`
      : "—";

  // IC significance from the 5d horizon edge
  let icSigStr = "—";
  if (h5 && !h5.insufficient && h5.ic_t_stat !== null && h5.ic_ir !== null) {
    const hurdle =
      h5.ic_t_gt3 === true
        ? "★★"
        : h5.ic_t_gt2 === true
          ? "★"
          : "";
    icSigStr = `t=${h5.ic_t_stat.toFixed(2)}${hurdle} (ICIR=${h5.ic_ir.toFixed(2)}, n=${h5.n_days})`;
  }

  // Out-of-sample (post frozen-panel-fix) IC — the honest forward test. Empty
  // until post-2026-07-12 sessions accrue, so it shows an 累积中 N/10 flag.
  const oosN = h5?.oos_n_days ?? 0;
  const _zh = locale === "zh";
  let oosStr = _zh ? `累积中 ${oosN}/10` : `accruing ${oosN}/10`;
  if (h5 && !h5.oos_insufficient && h5.oos_mean_ic !== null && h5.oos_mean_ic !== undefined) {
    oosStr = `IC=${h5.oos_mean_ic.toFixed(3)} (n=${oosN})`;
  }

  const isZh = locale === "zh";
  const label =
    isZh
      ? t(locale, "edge.honest_title")
      : t(locale, "edge.honest_title");

  return (
    <HoverTip
      content={t(locale, "edge.honest_tip").replace("{bps}", String(sb.cost_bps_used))}
      placement="bottom"
      width={320}
    >
      <div className="flex cursor-help flex-wrap items-center gap-x-3 gap-y-0.5 border-l border-tm-rule pl-4">
        <span className="font-tm-mono text-[11px] uppercase tracking-wide text-tm-muted">
          {label}
        </span>
        <span className="font-tm-mono text-[11px] tabular-nums text-tm-fg-2">
          {isZh
            ? `净收益(计成本) ${netPct} vs SPY ${spyPct}`
            : `net(cost) ${netPct} vs SPY ${spyPct}`}
        </span>
        <span className="font-tm-mono text-[11px] tabular-nums text-tm-muted">
          {isZh ? `换手 ${toStr}/日` : `to ${toStr}/d`}
        </span>
        <span className="font-tm-mono text-[11px] tabular-nums text-tm-muted">
          {isZh ? `盈亏平衡成本 ${beStr}` : `breakeven ${beStr}`}
        </span>
        <span className="font-tm-mono text-[11px] tabular-nums text-tm-muted">
          {isZh ? `IC t=${icSigStr}` : `IC ${icSigStr}`}
        </span>
        <span className="font-tm-mono text-[11px] tabular-nums text-tm-muted">
          {isZh ? `修复后样本外 ${oosStr}` : `OOS(post-fix) ${oosStr}`}
        </span>
      </div>
    </HoverTip>
  );
}

export default function BasketEdgeStrip({
  onOpenPaper,
}: {
  readonly onOpenPaper?: () => void;
}) {
  const { locale } = useLocale();
  const [data, setData] = useState<BasketEdgeResponse | null>(null);
  const [sb, setSb] = useState<PicksScoreboard | null>(null);
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
    // The realized scoreboard loads independently; null (not enough history)
    // or failure just means the segment doesn't render.
    fetchPicksScoreboard()
      .then((res) => {
        if (!cancelled) setSb(res);
      })
      .catch(() => undefined);
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
        <span className="font-tm-mono text-[12px] font-semibold uppercase tracking-wider text-tm-accent">
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

      {sb ? <ScoreboardCells sb={sb} /> : null}
      {sb && data ? (
        <HonestMetricsBlock
          sb={sb}
          h5={data.horizons.find((h) => h.horizon === 5)}
        />
      ) : null}

      {/* Paper Trading entry button — right side of strip */}
      {onOpenPaper ? (
        <button
          type="button"
          onClick={onOpenPaper}
          className="ml-auto flex shrink-0 items-center gap-2 rounded border border-tm-accent bg-tm-accent px-4 py-2 font-tm-mono text-[13px] font-semibold uppercase tracking-wide text-tm-bg shadow-sm transition-opacity hover:opacity-85 focus:outline-none focus:ring-1 focus:ring-tm-accent focus:ring-offset-1 focus:ring-offset-tm-bg-2"
        >
          <Wallet className="h-4 w-4" strokeWidth={1.75} />
          {t(locale, "sim.open_btn")}
        </button>
      ) : null}
    </div>
  );
}
