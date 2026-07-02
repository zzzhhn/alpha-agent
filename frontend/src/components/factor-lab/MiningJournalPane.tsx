import { TmPane } from "@/components/tm/TmPane";
import type { Locale } from "@/lib/i18n";
import type { MiningLesson } from "@/lib/api/factor-lab";

/**
 * Mining Journal — the visible face of the self-evolving miner's memory
 * (Phase A) and its self-correlation rejections (Phase B). Each row is one
 * distilled lesson the proposer wrote after evaluating a candidate:
 *   KEEP  (accepted) — a survivor worth extending
 *   WEAK  (weak)     — evaluated but below the keep gate
 *   AVOID (rejected) — failed validation, or a self-correlation duplicate
 * The proposer reads these back each round, so this panel is literally what
 * the agent has learned so far.
 */
const OUTCOME: Record<
  MiningLesson["outcome"],
  { readonly tag: string; readonly cls: string }
> = {
  accepted: { tag: "KEEP", cls: "border-tm-pos text-tm-pos" },
  weak: { tag: "WEAK", cls: "border-tm-warn text-tm-warn" },
  rejected: { tag: "AVOID", cls: "border-tm-neg text-tm-neg" },
};

export function MiningJournalPane({
  lessons,
  locale,
}: {
  readonly lessons: MiningLesson[];
  readonly locale: Locale;
}) {
  const counts = { accepted: 0, weak: 0, rejected: 0 };
  for (const l of lessons) counts[l.outcome] += 1;
  const meta = `${lessons.length} · ${counts.accepted} KEEP · ${counts.weak} WEAK · ${counts.rejected} AVOID`;

  return (
    <TmPane title="MINING.JOURNAL" meta={meta}>
      {lessons.length === 0 ? (
        <p className="px-3 py-4 font-tm-mono text-[11px] leading-relaxed text-tm-muted">
          {locale === "zh"
            ? "还没有挖矿经验。运行一次「提出因子」后，AI 每评估一个候选就会在这里写下一条经验（保留 / 偏弱 / 拒绝），下一轮它会读这些经验来避免重复、调整方向。"
            : "No lessons yet. Run a propose round — the agent writes one lesson per evaluated candidate here (KEEP / WEAK / AVOID), then reads them back next round to avoid repeats and shift direction."}
        </p>
      ) : (
        <ul className="flex flex-col divide-y divide-tm-rule">
          {lessons.map((l, i) => {
            const o = OUTCOME[l.outcome];
            return (
              <li key={i} className="flex items-start gap-3 px-3 py-2">
                <span
                  className={`mt-0.5 shrink-0 border px-1.5 py-px font-tm-mono text-[9px] font-bold tracking-[0.04em] ${o.cls}`}
                >
                  {o.tag}
                </span>
                <div className="min-w-0 flex-1">
                  <code className="block truncate font-tm-mono text-[11px] text-tm-accent">
                    {l.expression}
                  </code>
                  <p className="mt-0.5 text-[11px] leading-snug text-tm-fg-2">
                    {l.lesson}
                  </p>
                </div>
                {l.test_sharpe != null ? (
                  <span className="shrink-0 font-tm-mono text-[10px] tabular-nums text-tm-muted">
                    SR {l.test_sharpe >= 0 ? "+" : ""}
                    {l.test_sharpe.toFixed(2)}
                  </span>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </TmPane>
  );
}
