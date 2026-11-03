"use client";

import { useState } from "react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { TmInput, TmSelect } from "@/components/tm/TmField";
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
  const [tier, setTier] = useState("all");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const operatorsLabel = zh ? "算子" : "Operators";
  const operandsLabel = zh ? "操作数" : "Operands";
  const activeLabel = tab === "operators" ? operatorsLabel : operandsLabel;
  const labelCategory = (category: string) => (zh ? CATEGORIES[category] : undefined) ?? category.replaceAll("_", " ");
  const rows = (tab === "operators"
    ? catalog.operators.map((item) => ({
      ...item,
      example: item.example ?? item.signature ?? `${item.name}(…)`,
      detail: zh ? item.description_zh || item.function_zh || item.description_en : item.description_en || item.description_zh || item.function_zh,
    }))
    : catalog.operands.map((item) => ({
      ...item,
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
  const searchLabel = tab === "operators" ? (zh ? "搜索算子" : "Search operators") : (zh ? "搜索操作数" : "Search operands");

  return (
    <>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-tm-rule bg-tm-bg-2">
        <SegmentedTabs idBase={TABS} className="border-b-0" ariaLabel={zh ? "目录类型" : "Catalog type"}
          items={[
            { key: "operators", label: `${operatorsLabel} · ${catalog.tier_summary.operators.total}` },
            { key: "operands", label: `${operandsLabel} · ${catalog.tier_summary.operands.total}` },
          ]}
          active={tab} onChange={(next) => { if (next !== tab) { setTab(next); setQuery(""); setPage(1); } }} />
        <span className="px-3 pb-1 font-tm-mono text-xs text-tm-muted sm:pb-0">{zh ? "名称升序" : "Name A–Z"}</span>
      </div>
      {(["operators", "operands"] as const).map((kind) => (
        <div key={kind} id={`${TABS}-panel-${kind}`} role="tabpanel" aria-labelledby={`${TABS}-tab-${kind}`} hidden={tab !== kind}>
          {tab === kind && <>
            <div className="flex flex-wrap items-center gap-2 border-b border-tm-rule px-3 py-2">
              <TmInput type="search" value={query} onChange={(value) => { setQuery(value); setPage(1); }}
                aria-label={searchLabel} placeholder={searchLabel} className="min-w-0 flex-[1_1_12rem] sm:max-w-xs" />
              <TmSelect value={tier} onChange={(value) => { setTier(value); setPage(1); }}
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
                  <li key={row.name} className="min-w-0 bg-tm-bg">
                    <details className="group px-3 py-2.5">
                      <summary className="cursor-pointer font-tm-mono text-xs leading-5 text-tm-fg-2 focus-visible:outline focus-visible:outline-tm-accent">
                        <code className="break-all font-semibold text-tm-accent">{row.name}</code>
                        <span className="mt-0.5 flex flex-wrap items-baseline gap-x-2 pl-3 text-tm-muted">
                          <span>{labelCategory(row.category)}</span><span aria-hidden="true">·</span><span>{row.tier}</span>
                          {!row.implemented && <span className="text-tm-warn">{zh ? "未实现" : "Not implemented"}</span>}
                        </span>
                      </summary>
                      <div className="mt-2 space-y-1.5 border-t border-tm-rule pt-2 text-xs leading-relaxed text-tm-fg-2">
                        {row.example && <p className="break-words font-tm-mono">{row.example}</p>}
                        {row.detail && row.detail !== row.example && <p className="break-words">{row.detail}</p>}
                        {!row.example && !row.detail && <p className="text-tm-muted">{zh ? "目录未提供说明。" : "No description in the catalog."}</p>}
                      </div>
                    </details>
                  </li>
                ))}
              </ul>
            ) : <p role="status" className="px-3 py-6 text-xs text-tm-muted">{zh ? "没有匹配的条目。试试其他关键词或筛选条件。" : "No matches. Try another query or filter."}</p>}
            <DataPagination locale={locale} scope={activeLabel} page={current} pageSize={PAGE_SIZE} total={matches.length} onChange={setPage} />
          </>}
        </div>
      ))}
    </>
  );
}
