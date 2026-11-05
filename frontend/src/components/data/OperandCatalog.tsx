"use client";

import { useState } from "react";
import { ChevronRight } from "lucide-react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { TmInput, TmSelect } from "@/components/tm/TmField";
import { TmRowButton } from "@/components/tm/TmButton";
import { TmDialog } from "@/components/tm/TmDialog";
import { SegmentedTabs } from "@/components/ui/SegmentedTabs";
import type { OperandCatalogResponse } from "@/lib/types";
import { DataPagination } from "./DataControls";

type Tab = "operators" | "operands";
const PAGE_SIZE = 8;
const TABS = "data-catalog";
const CATEGORIES: Readonly<Record<string, string>> = {
  alt_data: "另类数据", analyst: "分析师", arithmetic: "算术", cross_section: "截面",
  fundamental: "基本面", group: "分组", logical: "逻辑", model: "模型", news: "新闻",
  option: "期权", price_volume: "价量", sentiment: "情绪", social_media: "社交媒体",
  time_series: "时间序列", transformational: "变换", vector: "向量", other: "其他",
};

export function OperandCatalog({ catalog }: { catalog: OperandCatalogResponse }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const [tab, setTab] = useState<Tab>("operators");
  const [tier, setTier] = useState("available");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const operatorsLabel = zh ? "算子" : "Operators";
  const operandsLabel = zh ? "操作数" : "Operands";
  const activeLabel = tab === "operators" ? operatorsLabel : operandsLabel;
  const labelCategory = (category: string) => (zh ? CATEGORIES[category] : undefined) ?? category.replaceAll("_", " ");
  const rows = (tab === "operators"
    ? catalog.operators.map((item, index) => ({
      ...item,
      rowKey: `operator:${index}`,
      example: item.example ?? item.signature ?? `${item.name}(…)`,
      detail: zh ? item.description_zh || item.function_zh || item.description_en : item.description_en || item.description_zh || item.function_zh,
    }))
    : catalog.operands.map((item, index) => ({
      ...item,
      rowKey: `operand:${index}`,
      category: item.category ?? "other",
      example: zh ? item.usage_zh || item.unit : item.unit || item.usage_zh,
      detail: zh ? item.description_zh || item.description_en : item.description_en || item.description_zh,
    }))).sort((a, b) => a.name.localeCompare(b.name));
  const needle = query.trim().toLowerCase();
  const matches = rows.filter((row) =>
    (tier === "all" || (tier === "available" ? row.implemented : row.tier === tier)) &&
    (!needle || [row.name, row.category, labelCategory(row.category), row.description_zh, row.description_en, row.example, row.detail]
      .some((value) => value?.toLowerCase().includes(needle))),
  );
  const current = Math.min(page, Math.max(1, Math.ceil(matches.length / PAGE_SIZE)));
  const visible = matches.slice((current - 1) * PAGE_SIZE, current * PAGE_SIZE);
  const selected = visible.find((row) => row.rowKey === selectedKey);
  const searchLabel = tab === "operators" ? (zh ? "搜索算子" : "Search operators") : (zh ? "搜索操作数" : "Search operands");

  return (
    <>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-tm-rule bg-tm-bg-2">
        <SegmentedTabs idBase={TABS} className="border-b-0" ariaLabel={zh ? "目录类型" : "Catalog type"}
          items={[
            { key: "operators", label: `${operatorsLabel} · ${catalog.tier_summary.operators.total}` },
            { key: "operands", label: `${operandsLabel} · ${catalog.tier_summary.operands.total}` },
          ]}
          active={tab} onChange={(next) => { if (next !== tab) { setSelectedKey(null); setTab(next); setQuery(""); setPage(1); } }} />
        <span className="px-3 pb-1 font-tm-mono text-xs text-tm-muted sm:pb-0">{zh ? "名称升序" : "Name A–Z"}</span>
      </div>
      {(["operators", "operands"] as const).map((kind) => (
        <div key={kind} id={`${TABS}-panel-${kind}`} role="tabpanel" aria-labelledby={`${TABS}-tab-${kind}`} hidden={tab !== kind}>
          {tab === kind && <>
            <div className="flex flex-wrap items-center gap-2 border-b border-tm-rule px-3 py-2">
              <TmInput type="search" value={query} onChange={(value) => { setSelectedKey(null); setQuery(value); setPage(1); }}
                aria-label={searchLabel} placeholder={searchLabel} className="min-w-0 flex-[1_1_12rem] sm:max-w-xs" />
              <TmSelect value={tier} onChange={(value) => { setSelectedKey(null); setTier(value); setPage(1); }}
                aria-label={zh ? "可用性与层级" : "Availability and tier"}
                options={[
                  { value: "all", label: zh ? "全部条目" : "All entries" },
                  { value: "available", label: zh ? "仅已实现" : "Implemented only" },
                  ...(["T1", "T2", "T3"].map((value) => ({ value, label: value }))),
                ]} />
            </div>
            {visible.length > 0 ? (
              <ul aria-label={activeLabel} className="grid gap-px bg-tm-rule sm:grid-cols-2 xl:grid-cols-4">
                {visible.map((row) => (
                  <li key={row.rowKey} className="min-w-0 bg-tm-bg">
                    <TmRowButton onClick={() => setSelectedKey(row.rowKey)} aria-haspopup="dialog" className="h-full px-3 py-2.5 font-tm-mono text-xs leading-5 text-tm-fg-2">
                      <span className="flex items-baseline justify-between gap-2">
                        <code className="break-all font-semibold text-tm-accent">{row.name}</code>
                        <ChevronRight aria-hidden="true" className="h-3.5 w-3.5 shrink-0 text-tm-muted" />
                      </span>
                      <span className="mt-0.5 flex flex-wrap items-baseline gap-x-2 text-tm-muted">
                        <span>{labelCategory(row.category)}</span><span aria-hidden="true">·</span><span>{row.tier}</span>
                        {!row.implemented && <span className="text-tm-warn">{zh ? "未实现" : "Not implemented"}</span>}
                      </span>
                    </TmRowButton>
                  </li>
                ))}
              </ul>
            ) : <p role="status" className="px-3 py-6 text-xs text-tm-muted">{zh ? "没有匹配的条目。试试其他关键词或筛选条件。" : "No matches. Try another query or filter."}</p>}
            <DataPagination locale={locale} scope={activeLabel} page={current} pageSize={PAGE_SIZE} total={matches.length} onChange={(next) => { setSelectedKey(null); setPage(next); }} />
          </>}
        </div>
      ))}
      <TmDialog open={!!selected} onClose={() => setSelectedKey(null)} title={selected?.name ?? ""}
        eyebrow={selected ? `${activeLabel} · ${labelCategory(selected.category)} · ${selected.tier}` : activeLabel}
        closeLabel={zh ? "关闭目录详情" : "Close catalog detail"} className="!max-w-[720px]">
        {selected && <div className="space-y-4 text-xs leading-relaxed text-tm-fg-2">
          {!selected.implemented && <p className="text-tm-warn">{zh ? "未实现" : "Not implemented"}</p>}
          {selected.example && <p className="border border-tm-rule bg-tm-bg-2 p-3 font-tm-mono [overflow-wrap:anywhere]">{selected.example}</p>}
          {selected.detail && selected.detail !== selected.example && <p className="[overflow-wrap:anywhere]">{selected.detail}</p>}
          {!selected.example && !selected.detail && <p className="text-tm-muted">{zh ? "目录未提供说明。" : "No description in the catalog."}</p>}
        </div>}
      </TmDialog>
    </>
  );
}
