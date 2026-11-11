"use client";
import { useState } from "react";
import type { GradeMethod } from "@/lib/api/picks";
import { gradeBand, gradeDimensionLabel } from "@/lib/grade-method";
import { TmButton } from "@/components/tm/TmButton";
import { TmDialog } from "@/components/tm/TmDialog";
import { getSignalDisplayLabel } from "@/lib/signal-labels";
import { type Locale } from "@/lib/i18n";
import { DIMENSION_ORDER } from "@/lib/grade-colors";
export default function GradeLegend({ method, hidden, locale }: { method?: GradeMethod; hidden?: ReadonlySet<string>; locale: Locale }) {
  const [open, setOpen] = useState(false); const zh = locale === "zh";
  return <>
    <TmButton variant="ghost" size="xs" aria-haspopup="dialog" onClick={() => setOpen(true)}>{zh ? "维度评级图例" : "Grade legend"}</TmButton>
    <TmDialog open={open} onClose={() => setOpen(false)} title={zh ? "A–F 维度评级" : "A–F dimension grades"} closeLabel={zh ? "关闭图例" : "Close legend"} className="!max-w-[680px]">
      <div className="space-y-3 text-sm leading-6 text-tm-fg-2">
        {method ? <>
          <p>{zh ? "有效成员信号取均值，再按完整股票池重新标准化。" : "Present live members are averaged, then re-standardized across the full universe."}</p>
          <div className="flex flex-wrap gap-x-4 gap-y-1 font-tm-mono text-xs">{method.bands.map(b => <span key={b.grade}>{b.grade}: {gradeBand(b.grade, method)}</span>)}</div>
          <p>{zh ? `至少 ${method.min_universe} 个观测；标准差下限 ${method.flatness_floor}。— 表示没有有效成员、观测不足、截面无差异或该股票缺少成员，不是 C 或 0。` : `At least ${method.min_universe} observations; standard-deviation floor ${method.flatness_floor}. — means no live member, too few observations, no spread or missing ticker members; never C or zero.`}</p>
          <ul className="divide-y divide-tm-rule">{DIMENSION_ORDER.map((d) => <li key={d.key} className="py-2"><span className="font-semibold">{gradeDimensionLabel(d.key, zh)}</span> · {(method.dimensions[d.key] ?? []).map(s => getSignalDisplayLabel(s, locale)).join(" / ")}{hidden?.has(d.key) ? <span className="block text-xs text-tm-muted">{zh ? "当前结果全部不可评级，表中已省略；原因可能为成员、样本或截面差异不足。" : "All current results are ungradeable; omitted from the table due to missing members, observations or spread."}</span> : null}</li>)}</ul>
          <p className="font-tm-mono text-xs text-tm-muted">{method.version}</p>
        </> : <p>{zh ? "该响应未记录评级方法，无法展示阈值。" : "This response did not record the grade method; thresholds are unavailable."}</p>}
      </div>
    </TmDialog>
  </>;
}
