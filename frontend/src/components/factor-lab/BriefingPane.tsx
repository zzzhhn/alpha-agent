"use client";

import { useMemo, useState } from "react";
import { TmPane } from "@/components/tm/TmPane";
import { TmPagination } from "@/components/tm/TmPagination";
import { BRIEFING_PAGE_SIZE, dedupeBriefingItems, paginateBriefingItems } from "@/components/evolution/observatory-model";
import type { Locale } from "@/lib/i18n";
import type { BriefingItem, MiningBriefing } from "@/lib/api/factor-lab";

/**
 * Phase D compressed briefing. The miner emits a lot; a human needs only three
 * buckets (XHS "Loop Engineering"):
 *   VALIDATED — pending proposals that passed cleanly. Clear extensions.
 *   FLAGGED   — passed the numbers but the skeptic / correlation gate raised a
 *               hand. Scrutinize before approving.
 *   AVOID     — recurring failure categories from the journal: where the search
 *               keeps hitting walls (counts of real outcomes, not speculation).
 */
function fmt(v: number | null | undefined, d = 2): string {
  return typeof v === "number" && !Number.isNaN(v) ? v.toFixed(d) : "—";
}

const RISK_CLS: Record<string, string> = {
  low: "border-tm-pos text-tm-pos",
  medium: "border-tm-warn text-tm-warn",
  high: "border-tm-neg text-tm-neg",
};

function SourceBadge({ source }: { source: string | null }) {
  if (!source) return null;
  return (
    <span className="shrink-0 border border-tm-rule px-1 py-px font-tm-mono text-xs uppercase tracking-[0.04em] text-tm-muted">
      {source}
    </span>
  );
}

function ItemRow({ item, flagged }: { item: BriefingItem; flagged: boolean }) {
  return (
    <li className="flex flex-col gap-1 px-3 py-2">
      <div className="flex items-center gap-2">
        <code className="min-w-0 flex-1 truncate font-tm-mono text-xs text-tm-fg">
          {item.expression}
        </code>
        <SourceBadge source={item.source} />
        {flagged && item.risk_level ? (
          <span
            className={`shrink-0 border px-1 py-px font-tm-mono text-xs font-bold uppercase ${RISK_CLS[item.risk_level] ?? RISK_CLS.medium}`}
          >
            {item.risk_level}
          </span>
        ) : null}
      </div>
      <div className="flex flex-wrap gap-x-3 font-mono text-xs text-tm-muted">
        <span>dSR {fmt(item.deflated_sharpe)}</span>
        <span>IC {fmt(item.ic_oos, 4)}</span>
        <span>self-corr {fmt(item.self_correlation)}</span>
      </div>
      {flagged && item.concerns.length > 0 ? (
        <ul className="list-disc pl-4 font-tm-mono text-xs text-tm-fg-2">
          {item.concerns.map((c, i) => (
            <li key={i}>{c}</li>
          ))}
        </ul>
      ) : null}
    </li>
  );
}

function Bucket({
  title,
  cls,
  empty,
  children,
}: {
  title: string;
  cls: string;
  empty: boolean;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div
        className={`border-b border-tm-rule px-3 py-1.5 font-tm-mono text-xs font-bold uppercase tracking-wider ${cls}`}
      >
        {title}
      </div>
      {empty ? (
        <p className="px-3 py-2 font-tm-mono text-xs text-tm-muted">—</p>
      ) : (
        children
      )}
    </div>
  );
}

export function BriefingPane({
  briefing,
  locale,
}: {
  readonly briefing: MiningBriefing;
  readonly locale: Locale;
}) {
  const zh = locale === "zh";
  const [page, setPage] = useState(1);
  const entries = useMemo(() => dedupeBriefingItems(briefing), [briefing]);
  const paginated = paginateBriefingItems(entries, page);
  const validated = entries.filter((entry) => !entry.flagged);
  const flagged = entries.filter((entry) => entry.flagged);
  const visibleValidated = paginated.items.filter((entry) => !entry.flagged);
  const visibleFlagged = paginated.items.filter((entry) => entry.flagged);
  const { failure_insights } = briefing;
  const meta = `${validated.length} ${locale === "zh" ? "通过" : "PASS"} · ${flagged.length} ${locale === "zh" ? "存疑" : "FLAG"} · ${failure_insights.length} ${locale === "zh" ? "规避" : "AVOID"}`;
  const isEmpty =
    validated.length === 0 &&
    flagged.length === 0 &&
    failure_insights.length === 0;

  const t = {
    validated: locale === "zh" ? "已验证 · 可扩展" : "VALIDATED · clear extensions",
    flagged: locale === "zh" ? "存疑 · 需审查" : "FLAGGED · scrutinize first",
    avoid:
      locale === "zh"
        ? "反复失败方向 · 规避"
        : "REPEATED FAILURES · what to avoid",
    empty:
      locale === "zh"
        ? "还没有 briefing。跑一轮「提出因子」或等每日 loop 运行后，这里会把结果压缩成三桶：直接可用 / 需审查 / 反复失败的方向。"
        : "No briefing yet. After a propose round or the daily loop runs, the miner's output is squeezed into three buckets here: ready to use / needs scrutiny / where the search keeps failing.",
  };

  return (
    <TmPane title="MINING.BRIEFING" meta={meta}>
      {isEmpty ? (
        <p className="px-3 py-4 font-tm-mono text-xs leading-relaxed text-tm-muted">
          {t.empty}
        </p>
      ) : (
        <div className="flex flex-col divide-y divide-tm-rule">
          <Bucket title={t.validated} cls="text-tm-pos" empty={visibleValidated.length === 0}>
            <ul className="flex flex-col divide-y divide-tm-rule">
              {visibleValidated.map(({ item }) => (
                <ItemRow key={item.id} item={item} flagged={false} />
              ))}
            </ul>
          </Bucket>
          <Bucket title={t.flagged} cls="text-tm-warn" empty={visibleFlagged.length === 0}>
            <ul className="flex flex-col divide-y divide-tm-rule">
              {visibleFlagged.map(({ item }) => (
                <ItemRow key={item.id} item={item} flagged={true} />
              ))}
            </ul>
          </Bucket>
          {entries.length > 0 ? <TmPagination
            page={page}
            pageSize={BRIEFING_PAGE_SIZE}
            totalItems={entries.length}
            pageSizeOptions={[BRIEFING_PAGE_SIZE]}
            onPageChange={setPage}
            onPageSizeChange={() => {}}
            labels={{
              navigation: zh ? "挖掘简报分页" : "Mining briefing pages",
              previous: "←", next: "→",
              previousAriaLabel: zh ? "上一页" : "Previous page",
              nextAriaLabel: zh ? "下一页" : "Next page",
              page: (current, count) => `${current} / ${count}`,
              pageSize: zh ? "每页" : "Per page",
              total: (count) => zh ? `去重后 ${count} 条` : `${count} unique items`,
            }}
          /> : null}
          <Bucket
            title={t.avoid}
            cls="text-tm-muted"
            empty={failure_insights.length === 0}
          >
            <ul className="flex flex-col divide-y divide-tm-rule">
              {failure_insights.map((f, i) => (
                <li
                  key={i}
                  className="flex items-center justify-between gap-3 px-3 py-2"
                >
                  <span className="min-w-0 flex-1 font-tm-mono text-xs text-tm-fg-2">
                    {f.pattern}
                  </span>
                  <span className="shrink-0 font-mono text-xs tabular-nums text-tm-neg">
                    ×{f.count}
                  </span>
                </li>
              ))}
            </ul>
          </Bucket>
        </div>
      )}
    </TmPane>
  );
}
