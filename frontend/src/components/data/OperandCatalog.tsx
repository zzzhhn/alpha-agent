"use client";

import { useState } from "react";
import { TmPane } from "@/components/tm/TmPane";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import type {
  CatalogTier,
  OperatorInfo,
  OperandInfo,
  OperandCatalogResponse,
} from "@/lib/types";

interface OperandCatalogProps {
  readonly catalog: OperandCatalogResponse;
}

type Tab = "operators" | "operands";
type TierFilter = "all" | "available" | CatalogTier;

const TIER_TONE: Record<CatalogTier, string> = {
  T1: "text-tm-pos",
  T2: "text-tm-warn",
  T3: "text-tm-muted",
};

// Label = implementation status, NOT tier-name. T1 and T2 are both live; the
// tier letter on the badge already conveys "which subset". T3 is the only
// not-implemented case.
function tierLabel(tier: CatalogTier, locale: "zh" | "en"): string {
  if (locale === "zh") {
    return tier === "T1"
      ? "基础可用"
      : tier === "T2"
        ? "扩展可用"
        : "未实现 (premium)";
  }
  return tier === "T1"
    ? "Core"
    : tier === "T2"
      ? "Extended"
      : "Unavailable";
}

export function OperandCatalog({ catalog }: OperandCatalogProps) {
  const { locale } = useLocale();
  const [tab, setTab] = useState<Tab>("operators");
  const [tierFilter, setTierFilter] = useState<TierFilter>("all");

  const opsSummary = catalog.tier_summary.operators;
  const fieldsSummary = catalog.tier_summary.operands;
  const summary = tab === "operators" ? opsSummary : fieldsSummary;

  return (
    <TmPane
      title={t(locale, "data.operands.title")}
      meta={
        <span className="font-tm-mono">
          <span className="text-tm-pos">T1 {summary.T1}</span> ·{" "}
          <span className="text-tm-warn">T2 {summary.T2}</span> ·{" "}
          <span className="text-tm-muted">T3 {summary.T3}</span> · total{" "}
          {summary.total}
        </span>
      }
    >
      <p className="px-3 pt-2.5 pb-2 font-tm-mono text-[11px] leading-relaxed text-tm-fg-2">
        {t(locale, "data.operands.subtitle")}
      </p>

      {/* Tab strip + tier filter — hairline divider matches pane head */}
      <div className="flex flex-wrap items-center gap-3 border-y border-tm-rule px-3 py-1.5 font-tm-mono">
        <div className="flex">
          <TabBtn
            active={tab === "operators"}
            onClick={() => setTab("operators")}
            label={`${t(locale, "data.operands.operatorsTab")} (${opsSummary.total})`}
          />
          <TabBtn
            active={tab === "operands"}
            onClick={() => setTab("operands")}
            label={`${t(locale, "data.operands.operandsTab")} (${fieldsSummary.total})`}
          />
        </div>
        <div className="ml-auto flex gap-0.5">
          {(["all", "available", "T1", "T2", "T3"] as TierFilter[]).map((tf) => (
            <button
              key={tf}
              type="button"
              onClick={() => setTierFilter(tf)}
              className={
                tierFilter === tf
                  ? "border border-tm-accent bg-tm-accent-soft px-2 py-0.5 text-[10.5px] uppercase tracking-[0.06em] text-tm-accent"
                  : "border border-tm-rule px-2 py-0.5 text-[10.5px] uppercase tracking-[0.06em] text-tm-muted hover:border-tm-rule-2 hover:text-tm-fg"
              }
            >
              {tf}
            </button>
          ))}
        </div>
      </div>

      <div className="px-3 py-3">
        {tab === "operators" ? (
          <OperatorList
            operators={filterOps(catalog.operators, tierFilter)}
            locale={locale}
          />
        ) : (
          <OperandList
            operands={filterOps(catalog.operands, tierFilter)}
            locale={locale}
          />
        )}
      </div>
    </TmPane>
  );
}

function filterOps<T extends { tier: CatalogTier; implemented: boolean }>(
  items: readonly T[],
  filter: TierFilter,
): readonly T[] {
  if (filter === "all") return items;
  if (filter === "available") return items.filter((it) => it.implemented);
  return items.filter((it) => it.tier === filter);
}

function TabBtn({
  active,
  onClick,
  label,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        active
          ? "border-b border-tm-accent px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.06em] text-tm-accent"
          : "border-b border-transparent px-3 py-1 text-[11px] uppercase tracking-[0.06em] text-tm-muted hover:text-tm-fg"
      }
    >
      {label}
    </button>
  );
}

function TierTag({
  tier,
  locale,
}: {
  tier: CatalogTier;
  locale: "zh" | "en";
}) {
  return (
    <span
      className={`border border-tm-rule px-1.5 py-px font-tm-mono text-[10px] uppercase tracking-[0.06em] ${TIER_TONE[tier]}`}
    >
      {tier} · {tierLabel(tier, locale)}
    </span>
  );
}

function OperatorList({
  operators,
  locale,
}: {
  operators: readonly OperatorInfo[];
  locale: "zh" | "en";
}) {
  const grouped = operators.reduce<Record<string, OperatorInfo[]>>(
    (acc, op) => {
      (acc[op.category] ??= []).push(op);
      return acc;
    },
    {},
  );
  if (operators.length === 0) {
    return (
      <p className="py-6 text-center font-tm-mono text-[11px] text-tm-muted">
        no items
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-4">
      {Object.entries(grouped).map(([cat, ops]) => (
        <section key={cat}>
          <h4 className="mb-2 font-tm-mono text-[10px] font-semibold uppercase tracking-[0.08em] text-tm-muted">
            {cat}
          </h4>
          <div className="grid grid-cols-1 gap-1.5 md:grid-cols-2">
            {ops.map((op) => (
              <div
                key={op.name}
                className={
                  "border border-tm-rule bg-tm-bg p-2 transition-colors hover:border-tm-rule-2 " +
                  (op.implemented ? "" : "opacity-60")
                }
                title={
                  op.implemented
                    ? undefined
                    : locale === "zh"
                      ? "未实现：需要 premium 数据源（向量数据/期权/新闻情绪等）"
                      : "Not implemented — requires premium data source (vector/options/news sentiment)"
                }
              >
                <div className="flex items-center justify-between gap-2">
                  <code className="font-tm-mono text-[12.5px] font-semibold text-tm-accent">
                    {op.name}
                  </code>
                  <div className="flex shrink-0 items-center gap-1">
                    {op.arity != null && (
                      <span className="border border-tm-rule px-1.5 py-px font-tm-mono text-[10px] uppercase tracking-[0.06em] text-tm-muted">
                        arity {op.arity}
                      </span>
                    )}
                    <TierTag tier={op.tier} locale={locale} />
                  </div>
                </div>
                <p className="mt-1.5 text-[11.5px] leading-relaxed text-tm-fg-2">
                  {op.description_zh ??
                    op.function_zh ??
                    op.description_en ??
                    ""}
                </p>
                {op.example && (
                  <code className="mt-1.5 block overflow-x-auto bg-tm-bg-3 px-2 py-1 font-tm-mono text-[11px] text-tm-muted">
                    {op.example}
                  </code>
                )}
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

function OperandList({
  operands,
  locale,
}: {
  operands: readonly OperandInfo[];
  locale: "zh" | "en";
}) {
  const grouped = operands.reduce<Record<string, OperandInfo[]>>((acc, op) => {
    const key = op.category ?? "other";
    (acc[key] ??= []).push(op);
    return acc;
  }, {});
  if (operands.length === 0) {
    return (
      <p className="py-6 text-center font-tm-mono text-[11px] text-tm-muted">
        no items
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-4">
      {Object.entries(grouped).map(([cat, fs]) => (
        <section key={cat}>
          <h4 className="mb-2 font-tm-mono text-[10px] font-semibold uppercase tracking-[0.08em] text-tm-muted">
            {cat}
          </h4>
          <div className="grid grid-cols-1 gap-1.5 md:grid-cols-2">
            {fs.map((op) => (
              <div
                key={op.name}
                className={
                  "border border-tm-rule bg-tm-bg p-2 transition-colors hover:border-tm-rule-2 " +
                  (op.implemented ? "" : "opacity-60")
                }
                title={
                  op.implemented
                    ? undefined
                    : locale === "zh"
                      ? "数据源未接入：需要 premium 数据集（如 RavenPack 新闻、Options 链、WorldQuant Model 字段等）"
                      : "Data source unavailable — requires premium dataset (RavenPack news, options chain, WorldQuant Model fields, etc.)"
                }
              >
                <div className="flex items-center justify-between gap-2">
                  <code className="font-tm-mono text-[12.5px] font-semibold text-tm-accent">
                    {op.name}
                  </code>
                  <TierTag tier={op.tier} locale={locale} />
                </div>
                <p className="mt-1.5 text-[11.5px] leading-relaxed text-tm-fg-2">
                  {op.description_zh ?? op.description_en ?? ""}
                </p>
                {op.usage_zh && (
                  <p className="mt-0.5 text-[10.5px] text-tm-muted">
                    {op.usage_zh}
                  </p>
                )}
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
