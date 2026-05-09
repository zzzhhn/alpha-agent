"use client";

/**
 * Operator + operand catalog — flat workstation pane.
 *
 * Renders as a single TmPane inside the TmScreen stack. Header carries
 * the tier counts (T1/T2/T3/total). Below the head: a hairline tab
 * strip (operators / operands) plus an inline tier-filter chip group.
 * Body groups items by category and renders each item as a 3-line
 * row (`tm-op` pattern from styles-screens.css):
 *   - name      (accent green)
 *   - signature (fg-2, smaller)
 *   - tier      (muted, small caps)
 *
 * No more "card-on-card" rounded grid — items are flat panels with
 * 1px gap-as-rule against the bg-tm-rule backdrop.
 */

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

function tierShort(tier: CatalogTier, locale: "zh" | "en"): string {
  if (locale === "zh") {
    return tier === "T1"
      ? "基础"
      : tier === "T2"
        ? "扩展"
        : "premium";
  }
  return tier === "T1" ? "core" : tier === "T2" ? "extended" : "premium";
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
      title="OPERATOR.CATALOG"
      meta={
        <span className="font-tm-mono">
          <span className="text-tm-pos">T1 {summary.T1}</span> ·{" "}
          <span className="text-tm-warn">T2 {summary.T2}</span> ·{" "}
          <span className="text-tm-muted">T3 {summary.T3}</span> · {summary.total} total
        </span>
      }
    >
      {/* Tab strip — `.tm-tabs` pattern */}
      <div className="flex border-b border-tm-rule bg-tm-bg-2">
        <TabBtn
          active={tab === "operators"}
          onClick={() => setTab("operators")}
          label={`${t(locale, "data.operands.operatorsTab")} · ${opsSummary.total}`}
        />
        <TabBtn
          active={tab === "operands"}
          onClick={() => setTab("operands")}
          label={`${t(locale, "data.operands.operandsTab")} · ${fieldsSummary.total}`}
        />
        {/* Tier filter — pushed right via flex-1 spacer */}
        <span className="flex-1" />
        <div className="flex items-center gap-px py-1.5 pr-2">
          {(["all", "available", "T1", "T2", "T3"] as TierFilter[]).map((tf) => (
            <button
              key={tf}
              type="button"
              onClick={() => setTierFilter(tf)}
              className={
                tierFilter === tf
                  ? "border border-tm-accent bg-tm-accent-soft px-2 py-px font-tm-mono text-[10px] uppercase tracking-[0.06em] text-tm-accent"
                  : "border border-tm-rule bg-tm-bg-2 px-2 py-px font-tm-mono text-[10px] uppercase tracking-[0.06em] text-tm-muted hover:text-tm-fg"
              }
            >
              {tf}
            </button>
          ))}
        </div>
      </div>

      <p className="px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
        {t(locale, "data.operands.subtitle")}
      </p>

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
          ? "border-r border-tm-rule border-b-2 border-b-tm-accent bg-tm-bg px-3.5 py-2 font-tm-mono text-[11px] uppercase tracking-[0.04em] text-tm-accent"
          : "border-r border-tm-rule px-3.5 py-2 font-tm-mono text-[11px] uppercase tracking-[0.04em] text-tm-muted hover:text-tm-fg"
      }
    >
      {label}
    </button>
  );
}

// Generic per-category section — used for both operators and operands.
function CategorySection({
  title,
  count,
  children,
}: {
  title: string;
  count: number;
  children: React.ReactNode;
}) {
  return (
    <section>
      <div className="border-t border-tm-rule px-3 py-1 font-tm-mono text-[10px] uppercase tracking-[0.10em] text-tm-muted first:border-t-0">
        {title} ({count})
      </div>
      <div className="grid gap-px bg-tm-rule p-px [grid-template-columns:repeat(auto-fill,minmax(220px,1fr))]">
        {children}
      </div>
    </section>
  );
}

function OperatorList({
  operators,
  locale,
}: {
  operators: readonly OperatorInfo[];
  locale: "zh" | "en";
}) {
  if (operators.length === 0) {
    return (
      <p className="px-3 py-6 text-center font-tm-mono text-[11px] text-tm-muted">
        no items
      </p>
    );
  }
  const grouped = operators.reduce<Record<string, OperatorInfo[]>>(
    (acc, op) => {
      (acc[op.category] ??= []).push(op);
      return acc;
    },
    {},
  );

  return (
    <>
      {Object.entries(grouped).map(([cat, ops]) => (
        <CategorySection key={cat} title={cat} count={ops.length}>
          {ops.map((op) => (
            <OpRow
              key={op.name}
              name={op.name}
              sig={op.example ?? `${op.name}(...)`}
              tier={op.tier}
              implemented={op.implemented}
              hint={
                op.description_zh ??
                op.function_zh ??
                op.description_en ??
                ""
              }
              locale={locale}
              kind="operator"
            />
          ))}
        </CategorySection>
      ))}
    </>
  );
}

function OperandList({
  operands,
  locale,
}: {
  operands: readonly OperandInfo[];
  locale: "zh" | "en";
}) {
  if (operands.length === 0) {
    return (
      <p className="px-3 py-6 text-center font-tm-mono text-[11px] text-tm-muted">
        no items
      </p>
    );
  }
  const grouped = operands.reduce<Record<string, OperandInfo[]>>((acc, op) => {
    const key = op.category ?? "other";
    (acc[key] ??= []).push(op);
    return acc;
  }, {});
  return (
    <>
      {Object.entries(grouped).map(([cat, fs]) => (
        <CategorySection key={cat} title={cat} count={fs.length}>
          {fs.map((op) => (
            <OpRow
              key={op.name}
              name={op.name}
              sig={op.usage_zh ?? op.name}
              tier={op.tier}
              implemented={op.implemented}
              hint={op.description_zh ?? op.description_en ?? ""}
              locale={locale}
              kind="operand"
            />
          ))}
        </CategorySection>
      ))}
    </>
  );
}

interface OpRowProps {
  readonly name: string;
  readonly sig: string;
  readonly tier: CatalogTier;
  readonly implemented: boolean;
  readonly hint: string;
  readonly locale: "zh" | "en";
  readonly kind: "operator" | "operand";
}

function OpRow({
  name,
  sig,
  tier,
  implemented,
  hint,
  locale,
  kind,
}: OpRowProps) {
  return (
    <div
      className={
        "flex flex-col gap-0.5 bg-tm-bg px-3 py-1.5 font-tm-mono " +
        (implemented ? "" : "opacity-50")
      }
      title={
        implemented
          ? hint || undefined
          : kind === "operator"
            ? locale === "zh"
              ? "未实现：需要 premium 数据源"
              : "not implemented — premium data source required"
            : locale === "zh"
              ? "数据源未接入：需要 premium 数据集"
              : "data source unavailable — premium dataset required"
      }
    >
      <span className={`text-[12px] font-semibold ${implemented ? "text-tm-accent" : "text-tm-muted"}`}>
        {name}
        {!implemented && " · planned"}
      </span>
      <span className="truncate text-[10.5px] text-tm-fg-2">{sig}</span>
      <span
        className={`text-[9.5px] uppercase tracking-[0.06em] ${TIER_TONE[tier]}`}
      >
        {tier} · {tierShort(tier, locale)}
      </span>
    </div>
  );
}
