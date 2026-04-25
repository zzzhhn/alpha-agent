"use client";

import { useState } from "react";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
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

const TIER_BADGE_VARIANT: Record<CatalogTier, "green" | "yellow" | "muted"> = {
  T1: "green",
  T2: "yellow",
  T3: "muted",
};

function tierLabel(tier: CatalogTier, locale: "zh" | "en"): string {
  if (locale === "zh") {
    return tier === "T1" ? "可用" : tier === "T2" ? "需 T2 数据" : "未实现";
  }
  return tier === "T1" ? "Available" : tier === "T2" ? "Needs T2 data" : "Unavailable";
}

export function OperandCatalog({ catalog }: OperandCatalogProps) {
  const { locale } = useLocale();
  const [tab, setTab] = useState<Tab>("operators");
  const [tierFilter, setTierFilter] = useState<TierFilter>("all");

  const opsSummary = catalog.tier_summary.operators;
  const fieldsSummary = catalog.tier_summary.operands;
  const summary = tab === "operators" ? opsSummary : fieldsSummary;

  return (
    <Card padding="md">
      <header className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-text">
            {t(locale, "data.operands.title")}
          </h2>
          <p className="mt-1 text-[11px] leading-relaxed text-muted">
            {t(locale, "data.operands.subtitle")}
          </p>
        </div>
        <div className="text-right text-[10px] text-muted">
          <div>
            <span className="font-mono text-green">T1 {summary.T1}</span> ·{" "}
            <span className="font-mono text-yellow">T2 {summary.T2}</span> ·{" "}
            <span className="font-mono text-muted">T3 {summary.T3}</span>
          </div>
          <div className="mt-0.5">total {summary.total}</div>
        </div>
      </header>

      <div className="mb-3 flex flex-wrap items-center gap-3 border-b border-border">
        <div className="flex gap-1">
          <TabBtn active={tab === "operators"} onClick={() => setTab("operators")}
            label={`${t(locale, "data.operands.operatorsTab")} (${opsSummary.total})`} />
          <TabBtn active={tab === "operands"} onClick={() => setTab("operands")}
            label={`${t(locale, "data.operands.operandsTab")} (${fieldsSummary.total})`} />
        </div>
        <div className="ml-auto flex gap-1 pb-2">
          {(["all", "available", "T1", "T2", "T3"] as TierFilter[]).map((tf) => (
            <button
              key={tf}
              type="button"
              onClick={() => setTierFilter(tf)}
              className={
                tierFilter === tf
                  ? "rounded bg-accent/15 px-2 py-0.5 font-mono text-[10px] text-accent"
                  : "rounded px-2 py-0.5 font-mono text-[10px] text-muted hover:bg-[var(--toggle-bg)] hover:text-text"
              }
            >
              {tf}
            </button>
          ))}
        </div>
      </div>

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
    </Card>
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

function TabBtn({ active, onClick, label }: {
  active: boolean; onClick: () => void; label: string;
}) {
  return (
    <button type="button" onClick={onClick}
      className={
        active
          ? "border-b-2 border-accent px-3 py-1.5 text-xs font-semibold text-accent"
          : "border-b-2 border-transparent px-3 py-1.5 text-xs text-muted hover:text-text"
      }>{label}</button>
  );
}

function TierBadge({ tier, locale }: { tier: CatalogTier; locale: "zh" | "en" }) {
  return (
    <Badge variant={TIER_BADGE_VARIANT[tier]} size="sm">
      {tier} · {tierLabel(tier, locale)}
    </Badge>
  );
}

function OperatorList({
  operators, locale,
}: { operators: readonly OperatorInfo[]; locale: "zh" | "en" }) {
  const grouped = operators.reduce<Record<string, OperatorInfo[]>>((acc, op) => {
    (acc[op.category] ??= []).push(op);
    return acc;
  }, {});
  if (operators.length === 0) {
    return <p className="py-6 text-center text-[11px] text-muted">no items</p>;
  }
  return (
    <div className="space-y-4">
      {Object.entries(grouped).map(([cat, ops]) => (
        <section key={cat}>
          <h4 className="mb-2 text-[10px] uppercase tracking-wide text-muted">{cat}</h4>
          <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
            {ops.map((op) => (
              <div key={op.name}
                className={
                  "rounded-md border border-border bg-[var(--card-inner,transparent)] p-2.5 " +
                  (op.implemented ? "" : "opacity-60")
                }
                title={op.implemented ? undefined : (locale === "zh" ? "尚未实现，将来通过外部数据源接入" : "Not implemented yet — premium / external data source needed")}>
                <div className="flex items-center justify-between gap-2">
                  <code className="font-mono text-xs font-semibold text-accent">{op.name}</code>
                  <div className="flex shrink-0 items-center gap-1">
                    {op.arity != null && (
                      <Badge variant="muted" size="sm">arity {op.arity}</Badge>
                    )}
                    <TierBadge tier={op.tier} locale={locale} />
                  </div>
                </div>
                <p className="mt-1 text-[11px] leading-relaxed text-text/90">
                  {op.description_zh ?? op.function_zh ?? op.description_en ?? ""}
                </p>
                {op.example && (
                  <code className="mt-1 block overflow-x-auto rounded bg-[var(--toggle-bg)] px-1.5 py-0.5 font-mono text-[10px] text-muted">
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
  operands, locale,
}: { operands: readonly OperandInfo[]; locale: "zh" | "en" }) {
  const grouped = operands.reduce<Record<string, OperandInfo[]>>((acc, op) => {
    const key = op.category ?? "other";
    (acc[key] ??= []).push(op);
    return acc;
  }, {});
  if (operands.length === 0) {
    return <p className="py-6 text-center text-[11px] text-muted">no items</p>;
  }
  return (
    <div className="space-y-4">
      {Object.entries(grouped).map(([cat, fs]) => (
        <section key={cat}>
          <h4 className="mb-2 text-[10px] uppercase tracking-wide text-muted">{cat}</h4>
          <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
            {fs.map((op) => (
              <div key={op.name}
                className={
                  "rounded-md border border-border bg-[var(--card-inner,transparent)] p-2.5 " +
                  (op.implemented ? "" : "opacity-60")
                }
                title={op.implemented ? undefined : (locale === "zh" ? "数据源未接入" : "Data source not available")}>
                <div className="flex items-center justify-between gap-2">
                  <code className="font-mono text-xs font-semibold text-accent">{op.name}</code>
                  <TierBadge tier={op.tier} locale={locale} />
                </div>
                <p className="mt-1 text-[11px] leading-relaxed text-text/90">
                  {op.description_zh ?? op.description_en ?? ""}
                </p>
                {op.usage_zh && (
                  <p className="mt-0.5 text-[10px] text-muted">{op.usage_zh}</p>
                )}
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
