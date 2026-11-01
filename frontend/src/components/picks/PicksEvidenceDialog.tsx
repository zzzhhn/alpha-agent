"use client";

import { useState } from "react";
import type { RatingCard } from "@/lib/api/picks";
import { t, type Locale } from "@/lib/i18n";
import { consistencyEvidence } from "@/lib/picks-evidence";
import { TmDialog } from "@/components/tm/TmDialog";
import { TmDisclosureButton } from "@/components/tm/TmButton";
import { TmTable, TmTableBody, TmTableCell, TmTableFrame, TmTableHead, TmTableHeaderCell, TmTableRow, TmTableRowHeader } from "@/components/tm/TmTable";

const WINDOWS = ["d5", "m1", "y1", "hist"] as const;
const LABELS = ["picks_table.cons_5d", "picks_table.cons_1m", "picks_table.cons_1y", "picks_table.cons_hist"] as const;
const pct = (value: number | null | undefined) => typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1 ? `${Math.round(value * 100)}%` : "—";

export function PicksEvidenceDetails({ card, locale }: { card: RatingCard; locale: Locale }) {
  const zh = locale === "zh";
  const [showHold, setShowHold] = useState(false);
  return <div className="space-y-4 text-sm leading-6 text-tm-fg-2">
    <p>{zh ? "比较已实现的次日涨跌方向与当时评级。窗口是回看范围，不是持有期限；HOLD 和尚未实现的结果不计入。" : "Compares realized next-day moves with the rating at the time. Windows are lookback periods, not holding periods. HOLD and unrealized outcomes are excluded."}</p>
    <TmTableFrame>
      <TmTable caption={zh ? "各窗口的历史方向证据" : "Historical direction evidence by window"} className="min-w-[480px]">
        <TmTableHead><TmTableRow>
          <TmTableHeaderCell>{zh ? "回看窗口" : "Lookback"}</TmTableHeaderCell>
          <TmTableHeaderCell textAlign="right">{zh ? "方向一致度" : "Direction hits"}</TmTableHeaderCell>
          <TmTableHeaderCell textAlign="right">{zh ? "有效 / 最低样本" : "Samples / minimum"}</TmTableHeaderCell>
          <TmTableHeaderCell>{zh ? "数据状态" : "Evidence status"}</TmTableHeaderCell>
        </TmTableRow></TmTableHead>
        <TmTableBody>{WINDOWS.map((window, index) => {
          const e = consistencyEvidence(card, window, locale);
          const status = e.n === null ? (zh ? "样本数未知" : "Count unknown")
            : e.n < e.min ? (zh ? "样本不足" : "Too few samples")
            : e.pct === null ? (zh ? "统计值待核验" : "Rate unavailable")
            : (zh ? "已记录" : "Recorded");
          return <TmTableRow key={window}>
            <TmTableRowHeader>{t(locale, LABELS[index])}</TmTableRowHeader>
            <TmTableCell numeric textAlign="right" className="text-sm">{e.pct === null ? "—" : `${e.pct}%`}</TmTableCell>
            <TmTableCell numeric textAlign="right">{e.n ?? "?"} / {e.min}</TmTableCell>
            <TmTableCell className={e.pct === null || e.n === null ? "text-tm-warn" : undefined}>{status}</TmTableCell>
          </TmTableRow>;
        })}</TmTableBody>
      </TmTable>
    </TmTableFrame>
    <p className="text-tm-muted">{zh ? "“—”不是 0%。低于最低样本数不展示比例；未知样本数的旧快照不能据此判断统计可靠性。历史一致度不代表未来胜率或收益。" : "A dash is not 0%. Rates below the sample minimum are withheld; legacy snapshots without counts cannot establish reliability. Historical agreement is not future win probability or return."}</p>
    <div className="grid gap-4 border-y border-tm-rule py-4 sm:grid-cols-2">
      <div><div className="flex justify-between gap-3"><span>{zh ? "信号一致度" : "Signal agreement"}</span><span className="font-tm-mono text-tm-fg">{pct(card.agreement)}</span></div><p className="mt-1 text-xs leading-5 text-tm-muted">{zh ? "当前各信号是否同向，不是历史命中率。" : "How aligned the current signals are, not a historical hit rate."}</p></div>
      <div><div className="flex justify-between gap-3"><span>{zh ? "5 日校准置信度" : "5D calibrated confidence"}</span><span className="font-tm-mono text-tm-fg">{pct(card.confidence)}</span></div><p className="mt-1 text-xs leading-5 text-tm-muted">{zh ? "另一持有期的模型校准值，不与上表混算。" : "Model calibration for a different horizon, separate from this table."}</p></div>
    </div>
    <div>
      <TmDisclosureButton expanded={showHold} onClick={() => setShowHold(v => !v)} aria-controls="picks-hold-evidence" label={zh ? "补充口径：包含 HOLD" : "Alternative: include HOLD"} />
      {showHold ? <div id="picks-hold-evidence" className="space-y-2 px-3 pt-3">
        <p>{zh ? "此口径将 HOLD 后次日涨跌在 ±0.5% 内视为命中，与上表分开记录。" : "This alternative counts HOLD as a hit when the next day's move stays within ±0.5%; it is separate from the table above."}</p>
        <div className="flex flex-wrap gap-x-6 gap-y-2 font-tm-mono text-sm">{(["d5", "m1"] as const).map((w, i) => <span key={w}>{t(locale, LABELS[i])}：{pct(card.consistency_hold?.[w])} <span className="text-tm-muted">n={card.consistency_hold_n?.[w] ?? "?"}</span></span>)}</div>
      </div> : null}
    </div>
  </div>;
}

export default function PicksEvidenceDialog({ card, locale, onClose }: { card: RatingCard; locale: Locale; onClose: () => void }) {
  const zh = locale === "zh";
  const snapshotDate = card.as_of ? new Date(card.as_of) : null;
  const snapshotTime = snapshotDate && Number.isFinite(snapshotDate.getTime())
    ? `${snapshotDate.toISOString().slice(0, 16).replace("T", " ")} UTC`
    : "—";
  return <TmDialog open onClose={onClose} title={`${card.ticker} · ${zh ? "历史方向证据" : "Historical direction evidence"}`} description={`${zh ? "快照时间" : "Snapshot"} ${snapshotTime}`} closeLabel={zh ? "关闭证据说明" : "Close evidence details"} className="!max-w-[760px]" bodyClassName="p-5">
    <PicksEvidenceDetails card={card} locale={locale} />
  </TmDialog>;
}
