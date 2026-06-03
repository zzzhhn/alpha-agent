"use client";

import { useMemo, useState } from "react";
import clsx from "clsx";
import type { RatingCard } from "@/lib/api/picks";
import type { SignalHealthEntry } from "@/lib/api/signal_health";
import {
  t,
  type TranslationKey,
} from "@/lib/i18n";
import { useLocale } from "@/components/layout/LocaleProvider";
import { getSignalDisplayLabel } from "@/lib/signal-labels";
import { InfoTooltip } from "@/components/ui/InfoTooltip";
import { useFactorMode } from "@/hooks/useFactorMode";
import { applyFactorMode } from "@/lib/picks-mode";

type SortKey = "signal" | "z" | "weight" | "contribution";

const TIER_DOT: Record<SignalHealthEntry["tier"], string> = {
  green: "bg-tm-pos",
  yellow: "bg-tm-warn",
  red: "bg-tm-neg",
  insufficient_data: "bg-tm-muted",
  unknown: "bg-tm-muted",
};

export default function AttributionTable({
  card,
  healthMap,
}: {
  card: RatingCard;
  // Pre-fetched in the parent RSC (Next Data Cache, 1h revalidate) so
  // every stock page used to re-fire /api/_health/signals client-side.
  // Empty map = upstream fetch failed; cells gracefully render "-".
  healthMap: Record<string, SignalHealthEntry>;
}) {
  const [sortKey, setSortKey] = useState<SortKey>("contribution");
  const [desc, setDesc] = useState(true);
  const { locale } = useLocale();
  const [factorMode, setFactorMode] = useFactorMode();

  // Apply factor-mode swap before sort so contribution-sort respects the
  // active mode. Picks endpoint already does composite re-rank server-side
  // when invoked with ?mode=long, but the single-card /api/stock response
  // does not — this swap is the per-component equivalent for stock detail.
  const breakdownForMode = useMemo(
    () => applyFactorMode(card.breakdown, factorMode),
    [card.breakdown, factorMode],
  );

  const sorted = useMemo(() => {
    const out = [...breakdownForMode];
    out.sort((a, b) => {
      const rawA = (a as unknown as Record<string, unknown>)[sortKey];
      const rawB = (b as unknown as Record<string, unknown>)[sortKey];
      // Null-safe numeric coercion: NaN/Inf were sanitized to null by the
      // storage layer; treat as 0 for ordering purposes.
      const numericKeys: SortKey[] = ["z", "weight", "contribution"];
      if (numericKeys.includes(sortKey)) {
        const av = typeof rawA === "number" ? rawA : 0;
        const bv = typeof rawB === "number" ? rawB : 0;
        return desc ? bv - av : av - bv;
      }
      return desc
        ? String(rawB).localeCompare(String(rawA))
        : String(rawA).localeCompare(String(rawB));
    });
    return out;
  }, [breakdownForMode, sortKey, desc]);

  const setSort = (k: SortKey) => {
    if (sortKey === k) {
      setDesc((d) => !d);
    } else {
      setSortKey(k);
      setDesc(true);
    }
  };

  // Locale-aware label strings for the mode toggle pill. Kept inline (not
  // in i18n.ts) since it's a small, component-local concern; the canonical
  // factor mode docs live in signal_tooltip.factor.
  const modeLabel = locale === "zh" ? "因子模式" : "FACTOR MODE";
  const modeShortLabel = locale === "zh" ? "短线" : "Short";
  const modeLongLabel = locale === "zh" ? "长线" : "Long";
  const modeTip =
    locale === "zh"
      ? "切换因子档的时间维度。短线 12d/60d 跟其他短窗口信号同步;长线 252d/126d 是学术经典。同步影响 Picks 排序 + 雷达图。"
      : "Toggle the factor signal's time horizon. Short (12d/60d) aligns with the other short-window legs; Long (252d/126d) is the academic standard. Syncs across Picks ranking + Radar.";

  // Honest empty-state for the Rank IC / ICIR / IR columns. signal_ic_history
  // is populated by the IC backtest engine; until that pipeline has
  // accumulated enough observations, every signal returns
  // tier="insufficient_data" / n_obs=0 and these three columns are all "—".
  // Without this note 12 rows of bare "—" read as "broken / forgotten"
  // rather than "accumulating".
  const icAvailable = sorted.some((b) => {
    const h = healthMap[b.signal];
    return (
      h != null &&
      (typeof h.icir_30d === "number" ||
        typeof h.ir_30d === "number" ||
        typeof h.live_ic_30d === "number")
    );
  });

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-end gap-2">
        {card.tier_flip_today ? (
          <span
            title={
              locale === "zh"
                ? "今日复合分轻微越过 tier 阈值,no-trade band 抑制了翻转。set ALPHA_TIER_BAND_Z 调整带宽。"
                : "Composite crossed a tier threshold marginally today; no-trade band suppressed the flip. Set ALPHA_TIER_BAND_Z to tune."
            }
            className="inline-flex items-center gap-1 rounded-md border border-tm-warn/40 bg-tm-warn/10 px-2 py-0.5 font-tm-sans text-[11px] text-tm-warn"
          >
            <span className="opacity-70">{locale === "zh" ? "无交易带" : "BAND"}</span>
            <span className="font-semibold">{locale === "zh" ? "生效" : "ACTIVE"}</span>
          </span>
        ) : null}
        <button
          type="button"
          onClick={() => setFactorMode(factorMode === "short" ? "long" : "short")}
          title={modeTip}
          className="inline-flex items-center gap-1.5 rounded-md border border-tm-accent/40 bg-tm-accent/10 px-2 py-0.5 font-tm-sans text-[11px] text-tm-accent transition hover:bg-tm-accent/20"
        >
          <span className="opacity-70">{modeLabel}</span>
          <span className="font-semibold">
            {factorMode === "short" ? modeShortLabel : modeLongLabel}
          </span>
        </button>
      </div>
      {!icAvailable ? (
        <div className="rounded border border-tm-rule bg-tm-bg-3/40 px-3 py-1.5 font-tm-sans text-[11px] leading-relaxed text-tm-muted">
          {t(locale, "attribution.ic_accumulating")}
        </div>
      ) : null}
      {/* P3-5: 10-column table scrolls horizontally on narrow screens
          instead of overflowing the card. */}
      <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] text-xs border-collapse">
        <thead>
        <tr className="text-tm-fg-2 border-b border-tm-rule">
          <SortTh
            onClick={() => setSort("signal")}
            active={sortKey === "signal"}
            desc={desc}
          >
            {t(locale, "attribution.signal")}
          </SortTh>
          <SortTh
            onClick={() => setSort("z")}
            active={sortKey === "z"}
            desc={desc}
            numeric
          >
            {t(locale, "attribution.z")}
          </SortTh>
          <SortTh
            onClick={() => setSort("weight")}
            active={sortKey === "weight"}
            desc={desc}
            numeric
          >
            {t(locale, "attribution.col_w")}
          </SortTh>
          <SortTh
            onClick={() => setSort("contribution")}
            active={sortKey === "contribution"}
            desc={desc}
            numeric
          >
            {t(locale, "attribution.contribution")}
          </SortTh>
          <th className="px-2 py-1.5 text-right text-tm-fg-2">
            <span className="inline-flex items-center gap-1">
              {t(locale, "attribution.live_ic")}
              <InfoTooltip content={t(locale, "attribution.tooltip_rank_ic")} />
            </span>
          </th>
          <th className="px-2 py-1.5 text-right text-tm-fg-2">
            <span className="inline-flex items-center gap-1">
              {t(locale, "attribution.icir")}
              <InfoTooltip content={t(locale, "attribution.tooltip_icir")} />
            </span>
          </th>
          <th className="px-2 py-1.5 text-right text-tm-fg-2">
            <span className="inline-flex items-center gap-1">
              {t(locale, "attribution.ir")}
              <InfoTooltip content={t(locale, "attribution.tooltip_ir")} />
            </span>
          </th>
          <th className="px-2 py-1.5 text-center text-tm-fg-2">
            {t(locale, "attribution.tier")}
          </th>
          <th className="px-2 py-1.5 text-left text-tm-fg-2">{t(locale, "attribution.col_source")}</th>
          <th className="px-2 py-1.5 text-left text-tm-fg-2">{t(locale, "attribution.col_time")}</th>
        </tr>
      </thead>
      <tbody>
        {sorted.map((b) => {
          const h = healthMap[b.signal];
          const tier: SignalHealthEntry["tier"] = h?.tier ?? "unknown";
          // Only the genuinely auto-dropped (red) tier should visually
          // grey out the row. insufficient_data also has weight_current
          // = 0 by definition, but its semantic meaning is "framework
          // alive, data accumulating" - dimming it reads as "this signal
          // is broken" which misleads the user. The gray tier dot already
          // communicates the early-life state without dimming.
          const isDropped = tier === "red";
          const isInsufficient = tier === "insufficient_data";
          const rowTooltip = isDropped
            ? t(locale, "attribution.dropped_tooltip")
            : isInsufficient
              ? t(locale, "attribution.insufficient_data_tooltip")
              : "";
          return (
            <tr
              key={b.signal}
              title={rowTooltip}
              className={clsx(
                "border-b border-tm-rule",
                isDropped ? "opacity-40" : "",
              )}
            >
              <td className="px-2 py-1 text-tm-fg">
                <span className="inline-flex items-center gap-1">
                  {getSignalDisplayLabel(b.signal, locale)}
                  <InfoTooltip
                    placement="right"
                    content={t(
                      locale,
                      `signal_tooltip.${b.signal}` as TranslationKey,
                    )}
                  />
                </span>
              </td>
              <td className="px-2 py-1 text-right font-mono text-tm-fg">
                {(() => {
                  const z = b.z ?? 0;
                  return `${z >= 0 ? "+" : ""}${z.toFixed(2)}`;
                })()}
              </td>
              <td className="px-2 py-1 text-right font-mono text-tm-fg">
                {(b.weight ?? 0).toFixed(2)}
              </td>
              <td
                className={clsx(
                  "px-2 py-1 text-right font-mono",
                  (b.contribution ?? 0) > 0
                    ? "text-tm-pos"
                    : (b.contribution ?? 0) < 0
                      ? "text-tm-neg"
                      : "text-tm-fg",
                )}
              >
                {(() => {
                  const c = b.contribution ?? 0;
                  return `${c >= 0 ? "+" : ""}${c.toFixed(2)}`;
                })()}
              </td>
              <td
                className="px-2 py-1 text-right font-mono text-tm-fg"
                title={
                  typeof h?.n_obs_30d === "number" && h.n_obs_30d > 0
                    ? `n_obs=${h.n_obs_30d}`
                    : undefined
                }
              >
                {typeof h?.live_ic_30d === "number"
                  ? `${h.live_ic_30d >= 0 ? "+" : ""}${h.live_ic_30d.toFixed(3)}`
                  : "-"}
              </td>
              <td className="px-2 py-1 text-right font-mono text-tm-fg">
                {typeof h?.icir_30d === "number"
                  ? `${h.icir_30d >= 0 ? "+" : ""}${h.icir_30d.toFixed(2)}`
                  : "-"}
              </td>
              <td className="px-2 py-1 text-right font-mono text-tm-fg">
                {typeof h?.ir_30d === "number"
                  ? `${h.ir_30d >= 0 ? "+" : ""}${h.ir_30d.toFixed(2)}`
                  : "-"}
              </td>
              <td className="px-2 py-1 text-center">
                <span
                  className={clsx(
                    "inline-block h-2 w-2 rounded-full",
                    TIER_DOT[tier],
                  )}
                  title={rowTooltip}
                />
              </td>
              <td className="px-2 py-1 text-tm-muted">{b.source}</td>
              <td className="px-2 py-1 text-tm-muted">
                {formatTimestamp(b.timestamp)}
              </td>
            </tr>
          );
        })}
      </tbody>
      </table>
      </div>
    </div>
  );
}

// Defensive timestamp formatter: legacy rows or partial responses can carry
// empty / malformed timestamp strings; `new Date("").toLocaleTimeString()`
// would render literal "Invalid Date" otherwise.
function formatTimestamp(raw: string | null | undefined): string {
  if (!raw) return "—";
  const d = new Date(raw);
  if (isNaN(d.getTime())) return "—";
  // Date + time: "06-02 06:31". A time-only "06:31" was ambiguous across the
  // multi-day staleness the data can have (some signals are reused for days).
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

function SortTh({
  children,
  onClick,
  active,
  desc,
  numeric,
}: {
  children: React.ReactNode;
  onClick: () => void;
  active: boolean;
  desc: boolean;
  numeric?: boolean;
}) {
  return (
    <th
      onClick={onClick}
      className={clsx(
        "cursor-pointer px-2 py-1.5 select-none",
        numeric ? "text-right" : "text-left",
        active ? "text-tm-fg" : "text-tm-fg-2",
      )}
    >
      {children}
      {active ? (desc ? " ▼" : " ▲") : ""}
    </th>
  );
}
