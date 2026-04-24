"use client";

import { useState } from "react";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import type {
  OperatorInfo,
  OperandInfo,
  OperandCatalogResponse,
} from "@/lib/types";

interface OperandCatalogProps {
  readonly catalog: OperandCatalogResponse;
}

type Tab = "operators" | "operands";

export function OperandCatalog({ catalog }: OperandCatalogProps) {
  const { locale } = useLocale();
  const [tab, setTab] = useState<Tab>("operators");

  return (
    <Card padding="md">
      <header className="mb-3">
        <h2 className="text-sm font-semibold text-text">
          {t(locale, "data.operands.title")}
        </h2>
        <p className="mt-1 text-[11px] leading-relaxed text-muted">
          {t(locale, "data.operands.subtitle")}
        </p>
      </header>

      <div className="mb-3 flex gap-1 border-b border-border">
        <TabBtn
          active={tab === "operators"}
          onClick={() => setTab("operators")}
          label={`${t(locale, "data.operands.operatorsTab")} (${catalog.operators.length})`}
        />
        <TabBtn
          active={tab === "operands"}
          onClick={() => setTab("operands")}
          label={`${t(locale, "data.operands.operandsTab")} (${catalog.operands.length})`}
        />
      </div>

      {tab === "operators" ? (
        <OperatorList operators={catalog.operators} locale={locale} />
      ) : (
        <OperandList operands={catalog.operands} locale={locale} />
      )}
    </Card>
  );
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
          ? "border-b-2 border-accent px-3 py-1.5 text-xs font-semibold text-accent"
          : "border-b-2 border-transparent px-3 py-1.5 text-xs text-muted hover:text-text"
      }
    >
      {label}
    </button>
  );
}

function OperatorList({
  operators,
  locale,
}: {
  operators: readonly OperatorInfo[];
  locale: "zh" | "en";
}) {
  const grouped = operators.reduce<Record<string, OperatorInfo[]>>((acc, op) => {
    (acc[op.category] ??= []).push(op);
    return acc;
  }, {});

  return (
    <div className="space-y-4">
      {Object.entries(grouped).map(([cat, ops]) => (
        <section key={cat}>
          <h4 className="mb-2 text-[10px] uppercase tracking-wide text-muted">
            {cat}
          </h4>
          <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
            {ops.map((op) => (
              <div
                key={op.name}
                className="rounded-md border border-border bg-[var(--card-inner,transparent)] p-2.5"
              >
                <div className="flex items-center justify-between gap-2">
                  <code className="font-mono text-xs font-semibold text-accent">
                    {op.name}
                  </code>
                  <Badge variant="muted" size="sm">
                    arity {op.arity}
                  </Badge>
                </div>
                <p className="mt-1 text-[11px] leading-relaxed text-text/90">
                  {locale === "zh" ? op.description_zh : op.description_en}
                </p>
                <code className="mt-1 block overflow-x-auto rounded bg-[var(--toggle-bg)] px-1.5 py-0.5 font-mono text-[10px] text-muted">
                  {op.example}
                </code>
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
  return (
    <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
      {operands.map((op) => (
        <div
          key={op.name}
          className="rounded-md border border-border bg-[var(--card-inner,transparent)] p-2.5"
        >
          <div className="flex items-center justify-between gap-2">
            <code className="font-mono text-xs font-semibold text-accent">
              {op.name}
            </code>
            {op.derived ? (
              <Badge variant="yellow" size="sm">
                {locale === "zh" ? "衍生" : "Derived"}
              </Badge>
            ) : (
              <Badge variant="green" size="sm">
                {locale === "zh" ? "原始" : "Raw"}
              </Badge>
            )}
          </div>
          <p className="mt-1 text-[11px] leading-relaxed text-text/90">
            {locale === "zh" ? op.description_zh : op.description_en}
          </p>
        </div>
      ))}
    </div>
  );
}
