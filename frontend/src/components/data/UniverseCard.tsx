"use client";

import { useId, useState, type ReactNode } from "react";
import Link from "next/link";
import { TmPane } from "@/components/tm/TmPane";
import { TmInput, TmSelect } from "@/components/tm/TmField";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { sectorLabel as localizedSector } from "@/lib/sector-label";
import type { UniverseInfo, CoverageResponse, FieldCoverage } from "@/lib/types";
import { DataPagination } from "./DataControls";

const CATEGORIES = {
  ohlcv: ["价量字段", "Price & volume"],
  metadata: ["元数据", "Metadata"],
  fundamental: ["基本面", "Fundamentals"],
} as const;
const percentage = (rate: number) => rate < 1 && rate >= 0.99995
  ? "<100%"
  : `${(rate * 100).toFixed(2)}%`;
const number = (value: number) => value.toLocaleString();

function fieldRate(field: FieldCoverage): number | null {
  return field.n_total > 0 ? field.n_present / field.n_total : null;
}

function CoverageMeter({ rate }: { rate: number | null }) {
  return (
    <span className="flex items-center gap-2.5">
      <span aria-hidden="true" className="hidden h-1.5 w-16 bg-tm-bg-3 sm:block">
        {rate !== null && <span
          className={`block h-full ${rate >= .99 ? "bg-tm-pos" : rate >= .85 ? "bg-tm-warn" : "bg-tm-neg"}`}
          style={{ width: `${rate * 100}%` }}
        />}
      </span>
      <span className="min-w-[4rem] text-right tabular-nums text-tm-fg">{rate === null ? "—" : percentage(rate)}</span>
    </span>
  );
}

function CoverageDisclosure({ title, meta, children, group }: { title: string; meta: ReactNode; children: ReactNode; group: string }) {
  return (
    <details name={group} className="border-b border-tm-rule last:border-b-0">
      <summary className="cursor-pointer px-3 py-2.5 font-tm-mono text-xs text-tm-fg-2 hover:bg-tm-bg-2 focus-visible:outline focus-visible:-outline-offset-2 focus-visible:outline-tm-accent">
        <span className="ml-1 inline-flex w-[calc(100%-1.5rem)] items-center justify-between gap-2 align-middle">
          <span>{title}</span>{meta}
        </span>
      </summary>
      <div className="divide-y divide-tm-rule border-t border-tm-rule bg-tm-bg-2 px-4 py-1">{children}</div>
    </details>
  );
}

export function UniverseOverview({ universe, closePct, children }: {
  universe: UniverseInfo;
  closePct: number | null;
  children?: ReactNode;
}) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  return (
    <TmPane title={t(locale, "data.coverage.title")} className="min-w-0">
      <div className="grid lg:grid-cols-2">
      <dl className="grid grid-cols-3 divide-x divide-tm-rule border-b border-tm-rule bg-tm-bg-2/40 font-tm-mono lg:border-b-0 lg:border-r">
        {[
          [zh ? "收盘价覆盖率" : "Close coverage", closePct === null ? "—" : percentage(closePct / 100)],
          [t(locale, "data.universe.tickerCount"), number(universe.ticker_count)],
          [t(locale, "data.universe.days"), number(universe.n_days)],
        ].map(([label, value], index) => (
          <div key={label} className="min-w-0 px-3 py-3 sm:px-4">
            <dt className="text-xs text-tm-muted">{label}</dt>
            <dd className={`mt-1 text-lg font-semibold tabular-nums sm:text-2xl ${index === 0 && closePct !== null ? closePct >= 99 ? "text-tm-pos" : "text-tm-warn" : "text-tm-fg"}`}>{value}</dd>
          </div>
        ))}
      </dl>
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] content-center gap-x-4 gap-y-1.5 px-4 py-3 font-tm-mono text-xs">
        <dt className="text-tm-muted">{t(locale, "data.universe.range")}</dt>
        <dd className="flex flex-wrap gap-x-2 tabular-nums text-tm-fg"><span>{universe.start_date}</span><span aria-hidden="true">→</span><span>{universe.end_date}</span></dd>
        <dt className="text-tm-muted">{t(locale, "data.universe.benchmark")}</dt>
        <dd className="break-words text-tm-fg">{universe.benchmark} · {universe.currency}</dd>
        {universe.name && universe.name !== universe.id && <>
          <dt className="text-tm-muted">{zh ? "样本" : "Sample"}</dt>
          <dd className="break-words text-tm-fg">{universe.name}</dd>
        </>}
      </dl>
      </div>
      {children}
    </TmPane>
  );
}

function CoverageFieldGroup({ fields, title, group }: { fields: FieldCoverage[]; title: string; group: string }) {
  const { locale } = useLocale();
  const [page, setPage] = useState(1);
  const pageSize = 8;
  const current = Math.min(page, Math.max(1, Math.ceil(fields.length / pageSize)));
  const rates = fields.map(fieldRate).filter((rate): rate is number => rate !== null);
  const average = rates.length ? rates.reduce((sum, rate) => sum + rate, 0) / rates.length : null;
  return <CoverageDisclosure group={group} title={title} meta={<CoverageMeter rate={average} />}>
    {fields.slice((current - 1) * pageSize, current * pageSize).map((field) => (
      <div key={field.name} className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 py-1.5 font-tm-mono text-xs">
        <code className="min-w-0 break-all text-tm-fg">{field.name}</code>
        <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-tm-muted">
          <span>{number(field.n_present)} / {number(field.n_total)}</span>
          <CoverageMeter rate={fieldRate(field)} />
        </span>
      </div>
    ))}
    {fields.length > pageSize && <DataPagination locale={locale} scope={title} page={current} pageSize={pageSize} total={fields.length} onChange={setPage} />}
  </CoverageDisclosure>;
}

/** Variable-length evidence belongs below the summary and roster, not inside
 * one side of a shared-height grid. Pagination preserves access to every field. */
export function UniverseCoverage({ coverage }: { coverage: CoverageResponse }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const group = useId();
  const [missingPage, setMissingPage] = useState(1);
  const lowCoverage = coverage.ticker_coverage.filter((row) => row.n_missing > 0);
  const missingPageSize = 6;
  const currentMissingPage = Math.min(missingPage, Math.max(1, Math.ceil(lowCoverage.length / missingPageSize)));

  return <TmPane title={zh ? "覆盖明细" : "Coverage detail"} meta={zh ? `${coverage.field_coverage.length} 个字段` : `${coverage.field_coverage.length} fields`}>
    {Object.entries(CATEGORIES).map(([category, labels]) => {
      const fields = coverage.field_coverage.filter((field) => field.category === category);
      if (!fields.length) return null;
      return <CoverageFieldGroup key={category} group={group} title={labels[zh ? 0 : 1]} fields={fields} />;
    })}
    {lowCoverage.length > 0 && (
      <CoverageDisclosure group={group} title={t(locale, "data.coverage.worstTickers")} meta={<span className="text-tm-warn">{zh ? `${lowCoverage.length} 只缺失` : `${lowCoverage.length} incomplete`}</span>}>
        {lowCoverage.slice((currentMissingPage - 1) * missingPageSize, currentMissingPage * missingPageSize).map((row) => (
          <div key={row.ticker} className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 py-1.5 font-tm-mono text-xs">
            <code className="text-tm-fg">{row.ticker}</code>
            <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-tm-muted">
              <span>{zh ? `缺 ${number(row.n_missing)} 条` : `${number(row.n_missing)} missing`}</span>
              <CoverageMeter rate={row.fill_rate} />
            </span>
          </div>
        ))}
        {lowCoverage.length > missingPageSize && (
          <DataPagination locale={locale} scope={t(locale, "data.coverage.worstTickers")} page={currentMissingPage} pageSize={missingPageSize} total={lowCoverage.length} onChange={setMissingPage} />
        )}
      </CoverageDisclosure>
    )}
    <p className="border-t border-tm-rule px-4 py-2.5 text-xs leading-relaxed text-tm-muted">
      {zh
        ? "总览按面板中非空收盘价计，分类按各字段覆盖率取平均。覆盖率不代表行情实时性。"
        : "The headline counts non-null panel closes. Categories average their field coverage; coverage does not measure freshness."}
    </p>
  </TmPane>;
}

const ROSTER_PAGE_SIZE = 16;

export function UniverseTickers({ universe }: { universe: UniverseInfo }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const title = t(locale, "data.universe.tickersLabel");
  const [query, setQuery] = useState("");
  const [sector, setSector] = useState("");
  const [page, setPage] = useState(1);
  const rows = universe.tickers.map((symbol, index) => ({
    symbol,
    sector: universe.sectors?.length === universe.tickers.length
      ? universe.sectors[index] || "Unknown"
      : null,
  })).sort((a, b) => a.symbol.localeCompare(b.symbol));
  const sectorLabel = (key: string) => localizedSector(key, locale);
  const counts = new Map<string, number>();
  for (const row of rows) if (row.sector) counts.set(row.sector, (counts.get(row.sector) ?? 0) + 1);
  const sectors = [...counts].sort(([a], [b]) => a === "Unknown" ? 1 : b === "Unknown" ? -1 : sectorLabel(a).localeCompare(sectorLabel(b), locale));
  const activeSector = counts.has(sector) ? sector : "";
  const needle = query.trim().toLowerCase();
  const matches = rows.filter((row) => (!activeSector || row.sector === activeSector) && row.symbol.toLowerCase().includes(needle));
  const current = Math.min(page, Math.max(1, Math.ceil(matches.length / ROSTER_PAGE_SIZE)));
  const visible = matches.slice((current - 1) * ROSTER_PAGE_SIZE, current * ROSTER_PAGE_SIZE);

  return (
    <TmPane title={title} meta={zh ? `${number(rows.length)} 只 · 代码升序` : `${number(rows.length)} symbols · A–Z`} className="min-w-0">
      <div className="flex flex-wrap gap-2 border-b border-tm-rule px-3 py-2">
        <TmInput type="search" value={query} onChange={(value) => { setQuery(value); setPage(1); }}
          aria-label={zh ? "搜索股票代码" : "Search ticker symbols"}
          placeholder={zh ? "搜索股票代码" : "Search tickers"} className="min-w-0 flex-[1_1_9rem]" />
        {sectors.length > 0 && <TmSelect value={activeSector} onChange={(value) => { setSector(value); setPage(1); }}
          aria-label={zh ? "按板块筛选" : "Filter by sector"} className="min-w-0 flex-[1_1_9rem] sm:flex-none"
          options={[
            { value: "", label: zh ? "全部板块" : "All sectors" },
            ...sectors.map(([key, count]) => ({ value: key, label: `${sectorLabel(key)} · ${number(count)}` })),
          ]} />}
      </div>
      {visible.length ? (
        <ul aria-label={title} className="grid grid-cols-2 gap-px bg-tm-rule sm:grid-cols-4 xl:grid-cols-8">
          {visible.map((row) => (
            <li key={row.symbol} className="min-w-0 bg-tm-bg px-3 py-1.5">
              <code className="block break-all text-xs font-semibold text-tm-fg">{row.symbol}</code>
              {row.sector && <span className="block text-xs leading-4 text-tm-muted">{sectorLabel(row.sector)}</span>}
            </li>
          ))}
        </ul>
      ) : <p role="status" className="px-3 py-6 text-xs text-tm-muted">{rows.length
        ? (zh ? "未找到匹配的股票。试试其他代码或板块。" : "No matching tickers. Try another symbol or sector.")
        : (zh ? "该股票池未返回成分股。" : "This universe returned no constituents.")}</p>}
      <DataPagination locale={locale} scope={title} page={current} pageSize={ROSTER_PAGE_SIZE} total={matches.length} onChange={setPage} />
      {activeSector === "Unknown" && (
        <p className="border-t border-tm-rule px-3 py-2 text-xs text-tm-muted">
          {zh ? "未返回板块信息，不等同于退市。" : "Missing sector data does not prove delisting."}{" "}
          <Link href="/methodology" className="text-tm-accent underline underline-offset-2">{zh ? "查看样本方法" : "See sample methodology"}</Link>
        </p>
      )}
    </TmPane>
  );
}
