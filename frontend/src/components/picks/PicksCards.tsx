"use client";

import Link from "next/link";
import type { RatingCard } from "@/lib/api/picks";
import { useLocale } from "@/components/layout/LocaleProvider";
import { getSignalDisplayLabel } from "@/lib/signal-labels";
import { consistencyEvidence } from "@/lib/picks-evidence";
import { TmButton } from "@/components/tm/TmButton";

const TONE: Record<string, string> = {
  BUY: "text-tm-pos",
  OW: "text-tm-pos",
  HOLD: "text-tm-fg-2",
  UW: "text-tm-neg",
  SELL: "text-tm-neg",
};

export default function PicksCards({
  picks,
  ranked,
  ordersDisabled,
  rankOffset = 0,
  onEvidenceOpen, onResearchOpen,
}: {
  readonly picks: readonly RatingCard[];
  readonly ranked: boolean;
  readonly ordersDisabled: boolean;
  readonly rankOffset?: number;
  readonly onResearchOpen?: (card: RatingCard) => void;
  readonly onEvidenceOpen: (card: RatingCard) => void;
}) {
  const { locale } = useLocale();
  return (
    <div className="divide-y divide-tm-rule" role="list">
      {picks.map((card, index) => {
        const score = card.rank_score ?? null;
        const d5 = consistencyEvidence(card, "d5", locale);
        const drivers = (card.top_drivers ?? []).slice(0, 2).map((name) => getSignalDisplayLabel(name, locale)).join(" · ");
        const name = locale === "zh" ? card.company_name_zh || card.company_name : card.company_name;
        return (
          <article key={card.ticker} className="space-y-3 px-3 py-4" role="listitem">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  {ranked ? <span className="font-tm-mono text-xs text-tm-muted">#{rankOffset + index + 1}</span> : null}
                  <Link href={`/stock/${card.ticker}`} prefetch={false} className="font-tm-mono text-base font-semibold text-tm-fg hover:text-tm-accent">{card.ticker}</Link>
                  <span className={`font-tm-mono text-xs font-semibold ${TONE[card.rating] ?? "text-tm-fg-2"}`}>{card.rating}</span>
                </div>
                {name ? <p className="mt-1 truncate text-xs text-tm-muted">{name}</p> : null}
              </div>
              <div className="text-right font-tm-mono tabular-nums">
                <div className="text-sm text-tm-fg">{score === null ? "—" : String(score)}</div>
                <div className="mt-1 text-xs text-tm-muted">{card.latest_price == null ? (locale === "zh" ? "收盘价未知" : "Close unavailable") : `$${card.latest_price.toFixed(2)}`}</div>
              </div>
            </div>
            <div className="grid grid-cols-3 gap-2 rounded-[2px] border border-tm-rule bg-tm-bg-2 px-3 py-2 font-tm-mono text-xs">
              <div><span className="text-tm-muted">{locale === "zh" ? "信号一致性" : "Signal agreement"}</span><div className="mt-1 text-tm-fg-2">{card.agreement == null ? "—" : `${Math.round(card.agreement * 100)}%`}</div></div>
              <div><span className="text-tm-muted">{locale === "zh" ? "近 5 日的次日命中率" : "Next-day hits, last 5 sessions"}</span><div className="mt-1 text-tm-fg-2">{d5.pct === null ? "—" : `${d5.pct}%`} · {d5.sampleLabel}</div></div>
              <div><span className="text-tm-muted">{locale === "zh" ? "5日校准置信度" : "5D calibrated confidence"}</span><div className="mt-1 text-tm-fg-2">{card.confidence == null ? "—" : `${Math.round(card.confidence * 100)}%`}</div></div>
            </div>
            {d5.pct === null ? <p className="text-xs leading-5 text-tm-muted">{d5.reason}</p> : null}
            <p className="min-h-5 text-xs leading-5 text-tm-fg-2">{drivers || (locale === "zh" ? "当前没有足够的有效驱动信号" : "Not enough active drivers")}</p>
            <div className="flex items-center justify-between gap-3">
              <span className="font-tm-mono text-xs text-tm-muted">{card.price_date ?? card.market_date ?? "—"}</span>
              {onResearchOpen ? <TmButton variant="ghost" size="sm" onClick={() => onResearchOpen(card)}>{locale === "zh" ? "研究记录" : "Research records"}</TmButton> : null}
              <TmButton variant="ghost" aria-haspopup="dialog" onClick={() => onEvidenceOpen(card)}>{locale === "zh" ? "证据说明" : "Evidence"}</TmButton>
              <Link
                href={ordersDisabled ? `/stock/${card.ticker}` : `/paper?ticker=${card.ticker}`}
                prefetch={false}
                className="border border-tm-accent px-3 py-1.5 font-tm-mono text-xs text-tm-accent hover:bg-tm-accent hover:text-tm-bg"
              >
                {ordersDisabled ? (locale === "zh" ? "查看研究" : "View research") : (locale === "zh" ? "进入组合决策" : "Open portfolio decision")}
              </Link>
            </div>
          </article>
        );
      })}
    </div>
  );
}
