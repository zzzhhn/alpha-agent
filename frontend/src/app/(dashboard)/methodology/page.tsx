"use client";

import { useCallback, useEffect, useState } from "react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import {
  fetchOperandCatalogWithSignatures,
  fetchSectors,
  fetchUniverses,
  fetchCoverage,
  invalidateDataCache,
} from "@/lib/api";
import type {
  OperandCatalogResponse,
  UniverseListResponse,
  CoverageResponse,
} from "@/lib/types";

type Tab = "data" | "operators" | "backtest";

interface OperatorWithSignature {
  readonly name: string;
  readonly category?: string;
  readonly tier?: string;
  readonly implemented?: boolean;
  readonly signature?: string;
  readonly source_snippet?: string;
}

export default function MethodologyPage() {
  const { locale } = useLocale();
  const [tab, setTab] = useState<Tab>("data");
  const [universes, setUniverses] = useState<UniverseListResponse | null>(null);
  const [coverage, setCoverage] = useState<CoverageResponse | null>(null);
  const [sectors, setSectors] = useState<readonly string[]>([]);
  const [catalog, setCatalog] = useState<OperandCatalogResponse | null>(null);
  // Errors are tracked per-fetch so the static Backtest tab never sees them
  // and so a retry can target the failing slice without re-fetching the rest.
  const [universesError, setUniversesError] = useState<string | null>(null);
  const [coverageError, setCoverageError] = useState<string | null>(null);
  const [sectorsError, setSectorsError] = useState<string | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [reloading, setReloading] = useState(false);

  const loadDataTab = useCallback(async (force = false) => {
    setReloading(true);
    if (force) invalidateDataCache();
    setUniversesError(null);
    setCoverageError(null);
    setSectorsError(null);
    const [u, c, s] = await Promise.all([
      fetchUniverses({ force }),
      fetchCoverage("SP500_subset", { force }),
      fetchSectors(),
    ]);
    if (u.error) setUniversesError(u.error); else if (u.data) setUniverses(u.data);
    if (c.error) setCoverageError(c.error); else if (c.data) setCoverage(c.data);
    if (s.error) setSectorsError(s.error); else if (s.data) setSectors(s.data.sectors);
    setReloading(false);
  }, []);

  const loadOperatorsTab = useCallback(async () => {
    setReloading(true);
    setCatalogError(null);
    const r = await fetchOperandCatalogWithSignatures();
    if (r.error) setCatalogError(r.error);
    else if (r.data) setCatalog(r.data);
    setReloading(false);
  }, []);

  useEffect(() => {
    void loadDataTab(false);
  }, [loadDataTab]);

  useEffect(() => {
    if (tab !== "operators" || catalog !== null) return;
    void loadOperatorsTab();
  }, [tab, catalog, loadOperatorsTab]);

  const dataTabHasError = Boolean(universesError || coverageError || sectorsError);

  return (
    <div className="flex flex-col gap-4 p-6">
      <header>
        <h1 className="text-2xl font-semibold text-text">
          {t(locale, "methodology.title")}
        </h1>
        <p className="mt-1 max-w-3xl text-[14px] leading-relaxed text-muted">
          {t(locale, "methodology.subtitle")}
        </p>
      </header>

      <div className="flex gap-1 border-b border-border">
        {(["data", "operators", "backtest"] as Tab[]).map((tk) => (
          <button
            key={tk}
            type="button"
            onClick={() => setTab(tk)}
            className={
              tab === tk
                ? "border-b-2 border-accent px-4 py-2 text-[14px] font-semibold text-accent"
                : "border-b-2 border-transparent px-4 py-2 text-[14px] text-muted hover:text-text"
            }
          >
            {t(locale, `methodology.tab.${tk}` as Parameters<typeof t>[1])}
          </button>
        ))}
      </div>

      {tab === "data" && dataTabHasError && (
        <ErrorCard
          title={t(locale, "methodology.error")}
          messages={[universesError, coverageError, sectorsError].filter(Boolean) as string[]}
          onRetry={() => loadDataTab(true)}
          retrying={reloading}
        />
      )}
      {tab === "operators" && catalogError && (
        <ErrorCard
          title={t(locale, "methodology.error")}
          messages={[catalogError]}
          onRetry={loadOperatorsTab}
          retrying={reloading}
        />
      )}

      {tab === "data" && (
        <DataTab universes={universes} coverage={coverage} sectors={sectors} />
      )}
      {tab === "operators" && <OperatorsTab catalog={catalog} />}
      {tab === "backtest" && <BacktestTab />}
    </div>
  );
}

/* ── Data tab ─────────────────────────────────────────────────────── */

function DataTab({
  universes, coverage, sectors,
}: {
  readonly universes: UniverseListResponse | null;
  readonly coverage: CoverageResponse | null;
  readonly sectors: readonly string[];
}) {
  const { locale } = useLocale();
  const u = universes?.universes[0];

  return (
    <div className="flex flex-col gap-4">
      <Card padding="md">
        <h2 className="mb-3 text-base font-semibold text-text">
          {t(locale, "methodology.data.panelTitle")}
        </h2>
        {u && coverage ? (
          <dl className="grid grid-cols-[160px_1fr] gap-y-2 text-[14px]">
            <Row label={t(locale, "methodology.data.universe")} value={u.name} mono />
            <Row label={t(locale, "methodology.data.tickers")} value={`${u.ticker_count}`} mono />
            <Row label={t(locale, "methodology.data.benchmark")} value={u.benchmark} mono />
            <Row label={t(locale, "methodology.data.range")} value={`${u.start_date} → ${u.end_date}`} mono />
            <Row label={t(locale, "methodology.data.days")} value={`${u.n_days}`} mono />
            <Row label={t(locale, "methodology.data.currency")} value={u.currency} mono />
            <Row label={t(locale, "methodology.data.ohlcvCoverage")}
              value={`${coverage.ohlcv_coverage_pct.toFixed(2)}%`} mono />
          </dl>
        ) : (
          <p className="text-muted">{t(locale, "common.loading")}</p>
        )}
      </Card>

      <Card padding="md">
        <h2 className="mb-3 text-base font-semibold text-text">
          {t(locale, "methodology.data.sectorsTitle")}
        </h2>
        <p className="mb-2 text-[13px] text-muted">
          {t(locale, "methodology.data.sectorsSubtitle")}
        </p>
        <div className="flex flex-wrap gap-2">
          {sectors.map((s) => (
            <code key={s} className="rounded bg-[var(--toggle-bg)] px-2 py-1 text-[13px] text-text">
              {s}
            </code>
          ))}
        </div>
      </Card>

      <Card padding="md">
        <h2 className="mb-3 text-base font-semibold text-text">
          {t(locale, "methodology.data.pipelineTitle")}
        </h2>
        <ol className="ml-5 list-decimal space-y-2 text-[14px] leading-relaxed text-text">
          <li>{t(locale, "methodology.data.step1")}</li>
          <li>{t(locale, "methodology.data.step2")}</li>
          <li>{t(locale, "methodology.data.step3")}</li>
          <li>{t(locale, "methodology.data.step4")}</li>
          <li>{t(locale, "methodology.data.step5")}</li>
        </ol>
      </Card>
    </div>
  );
}

/* ── Operators tab ────────────────────────────────────────────────── */

function OperatorsTab({ catalog }: { readonly catalog: OperandCatalogResponse | null }) {
  const { locale } = useLocale();
  if (!catalog) {
    return <Card padding="md"><p className="text-muted">{t(locale, "common.loading")}</p></Card>;
  }
  const ops = catalog.operators as OperatorWithSignature[];
  const implemented = ops.filter((o) => o.implemented);
  const byCategory = new Map<string, OperatorWithSignature[]>();
  for (const op of implemented) {
    const cat = op.category ?? "uncategorized";
    if (!byCategory.has(cat)) byCategory.set(cat, []);
    byCategory.get(cat)!.push(op);
  }

  return (
    <div className="flex flex-col gap-4">
      <Card padding="md">
        <h2 className="mb-2 text-base font-semibold text-text">
          {t(locale, "methodology.operators.title")}
        </h2>
        <p className="text-[13px] text-muted">
          {t(locale, "methodology.operators.subtitle")
            .replace("{n}", String(implemented.length))
            .replace("{total}", String(ops.length))}
        </p>
      </Card>

      {Array.from(byCategory.entries()).sort((a, b) => a[0].localeCompare(b[0])).map(([cat, list]) => (
        <Card key={cat} padding="md">
          <h3 className="mb-3 text-[14px] font-semibold uppercase tracking-wide text-muted">
            {cat} <span className="ml-2 text-[12px] normal-case text-muted">({list.length})</span>
          </h3>
          <div className="space-y-3">
            {list.map((op) => (
              <details key={op.name} className="rounded border border-border">
                <summary className="cursor-pointer px-3 py-2 font-mono text-[13px] text-text hover:bg-[var(--toggle-bg)]">
                  {op.signature ?? op.name}
                </summary>
                {op.source_snippet && (
                  <pre className="m-0 overflow-x-auto rounded-b bg-[var(--toggle-bg)] px-3 py-2 font-mono text-[12px] leading-relaxed text-muted">
                    {op.source_snippet}
                  </pre>
                )}
              </details>
            ))}
          </div>
        </Card>
      ))}
    </div>
  );
}

/* ── Backtest tab ─────────────────────────────────────────────────── */

function BacktestTab() {
  const { locale } = useLocale();

  // Each row is one of the 6 KPIs the backtest engine returns. The text is
  // intentionally written as the formula itself + the file:line where it lives,
  // so when the engine changes the user can git blame the same line.
  const rows: { keyBase: string; formula: string; ref: string }[] = [
    { keyBase: "sharpe", formula: "Sharpe = mean(daily_ret) / std(daily_ret) × √252", ref: "factor_backtest.py L282" },
    { keyBase: "totalReturn", formula: "Total return = ∏(1 + daily_ret) − 1 over the slice", ref: "factor_backtest.py L279" },
    { keyBase: "ic", formula: "IC = mean of cross-sectional Spearman(rank(factor[t]), rank(fwd_ret[t])) across t", ref: "kernel.py spearman_ic" },
    { keyBase: "mdd", formula: "MaxDD = min((cumprod(1+r) − running_max) / running_max) over the slice", ref: "factor_backtest.py L256" },
    { keyBase: "turnover", formula: "Turnover = mean(L1 norm of weight delta between consecutive rows)", ref: "factor_backtest.py L301" },
    { keyBase: "hitRate", formula: "Hit rate = fraction of days with daily IC > 0", ref: "factor_backtest.py L293" },
  ];

  return (
    <div className="flex flex-col gap-4">
      <Card padding="md">
        <h2 className="mb-2 text-base font-semibold text-text">
          {t(locale, "methodology.backtest.title")}
        </h2>
        <p className="text-[13px] leading-relaxed text-muted">
          {t(locale, "methodology.backtest.subtitle")}
        </p>
      </Card>

      <Card padding="md">
        <h3 className="mb-3 text-[14px] font-semibold text-text">
          {t(locale, "methodology.backtest.kpiTitle")}
        </h3>
        <table className="w-full text-[13px]">
          <thead className="bg-[var(--toggle-bg)]">
            <tr>
              <th className="px-2 py-1.5 text-left font-medium text-muted">{t(locale, "methodology.backtest.colMetric")}</th>
              <th className="px-2 py-1.5 text-left font-medium text-muted">{t(locale, "methodology.backtest.colFormula")}</th>
              <th className="px-2 py-1.5 text-left font-medium text-muted">{t(locale, "methodology.backtest.colRef")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.keyBase} className="border-t border-border">
                <td className="px-2 py-1.5 font-mono text-text">
                  {t(locale, `methodology.backtest.${r.keyBase}` as Parameters<typeof t>[1])}
                </td>
                <td className="px-2 py-1.5 font-mono text-[12px] text-muted">{r.formula}</td>
                <td className="px-2 py-1.5 font-mono text-[12px] text-muted">{r.ref}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card padding="md">
        <h3 className="mb-3 text-[14px] font-semibold text-text">
          {t(locale, "methodology.backtest.portfolioTitle")}
        </h3>
        <ul className="ml-5 list-disc space-y-1.5 text-[13px] leading-relaxed text-text">
          <li>{t(locale, "methodology.backtest.portfolio1")}</li>
          <li>{t(locale, "methodology.backtest.portfolio2")}</li>
          <li>{t(locale, "methodology.backtest.portfolio3")}</li>
          <li>{t(locale, "methodology.backtest.portfolio4")}</li>
        </ul>
      </Card>
    </div>
  );
}

/* ── Helpers ──────────────────────────────────────────────────────── */

function ErrorCard({
  title, messages, onRetry, retrying,
}: {
  readonly title: string;
  readonly messages: readonly string[];
  readonly onRetry: () => void;
  readonly retrying: boolean;
}) {
  const { locale } = useLocale();
  // Dedupe — when multiple parallel fetches hit the same edge IP poisoning
  // they often produce the identical TypeError text; one card row is plenty.
  const unique = Array.from(new Set(messages));
  return (
    <Card padding="md">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-base font-semibold text-red">{title}</p>
          <ul className="mt-1 list-disc pl-5 text-[13px] leading-relaxed text-text">
            {unique.map((m, i) => (
              <li key={i}>{m}</li>
            ))}
          </ul>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={onRetry}
          disabled={retrying}
        >
          {retrying ? t(locale, "methodology.retrying") : t(locale, "methodology.retry")}
        </Button>
      </div>
    </Card>
  );
}

function Row({
  label, value, mono,
}: {
  readonly label: string;
  readonly value: string;
  readonly mono?: boolean;
}) {
  return (
    <>
      <dt className="text-muted">{label}</dt>
      <dd className={mono ? "font-mono text-text" : "text-text"}>{value}</dd>
    </>
  );
}
