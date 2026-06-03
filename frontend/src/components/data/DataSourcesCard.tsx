"use client";

import { useEffect, useState } from "react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t, type Locale } from "@/lib/i18n";
import { TmPane } from "@/components/tm/TmPane";
import { fetchDataSources, type DataSourceStat } from "@/lib/api/data_sources";

// Live ingest sources. Kept in sync with the signal pipeline: Finnhub (earnings
// -> Catalyst) and SEC EDGAR (Form 4 -> Insider) were added 2026-06; both run
// as daily GitHub-Actions crons that prime the signal cache. `signal` is the
// dimension each source powers (the same codes shown in the attribution radar);
// `key` maps to the /api/_health/data_sources stat so the DATA column shows the
// real row count + freshness, not just that the source is configured.
interface SourceRow {
  readonly name: string;
  readonly key: string;
  readonly feedsKey: I18nKey;
  readonly signal: string;
  readonly cadenceKey: I18nKey;
}

type I18nKey = Parameters<typeof t>[1];

const SOURCES: readonly SourceRow[] = [
  { name: "yfinance", key: "yfinance", feedsKey: "data.src.yf", signal: "Technicals · Analyst · Options", cadenceKey: "data.cadence.intraday" },
  { name: "FRED", key: "fred", feedsKey: "data.src.fred", signal: "Macro", cadenceKey: "data.cadence.daily" },
  { name: "Finnhub", key: "finnhub", feedsKey: "data.src.finnhub", signal: "Catalyst", cadenceKey: "data.cadence.daily" },
  { name: "SEC EDGAR", key: "edgar", feedsKey: "data.src.edgar", signal: "Insider", cadenceKey: "data.cadence.daily" },
  { name: "RSS / Yahoo", key: "news", feedsKey: "data.src.news", signal: "News", cadenceKey: "data.cadence.intraday" },
];

export function DataSourcesCard() {
  const { locale } = useLocale();
  const [stats, setStats] = useState<Record<string, DataSourceStat | null> | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchDataSources()
      .then((r) => {
        if (!cancelled) setStats(r.sources);
      })
      .catch(() => {
        if (!cancelled) setStats({});
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <TmPane title="DATA.SOURCES" meta={`${SOURCES.length} PROVIDERS`}>
      <div
        className="grid gap-px bg-tm-rule"
        style={{ gridTemplateColumns: "minmax(100px,130px) 1fr minmax(100px,140px) minmax(56px,72px) minmax(110px,150px)" }}
      >
        <Cell head>SOURCE</Cell>
        <Cell head>{t(locale, "data.src.col_feeds")}</Cell>
        <Cell head>SIGNAL</Cell>
        <Cell head>{t(locale, "data.src.col_cadence")}</Cell>
        <Cell head>{t(locale, "data.src.col_data")}</Cell>
        {SOURCES.map((s) => (
          <Row key={s.name} locale={locale} src={s} stat={stats?.[s.key]} loaded={stats !== null} />
        ))}
      </div>
    </TmPane>
  );
}

function Row({
  locale,
  src,
  stat,
  loaded,
}: {
  locale: Locale;
  src: SourceRow;
  stat: DataSourceStat | null | undefined;
  loaded: boolean;
}) {
  return (
    <>
      <Cell>
        <span className="font-tm-mono text-[12px] text-tm-fg">{src.name}</span>
      </Cell>
      <Cell>
        <span className="text-[13px] text-tm-fg-2">{t(locale, src.feedsKey)}</span>
      </Cell>
      <Cell>
        <span className="font-tm-mono text-[11px] text-tm-accent">{src.signal}</span>
      </Cell>
      <Cell>
        <span className="text-[11px] text-tm-muted">{t(locale, src.cadenceKey)}</span>
      </Cell>
      <Cell>
        <DataStat locale={locale} stat={stat} loaded={loaded} />
      </Cell>
    </>
  );
}

// The live data presence for a source: row count + how fresh the last write is.
// FRED is live-fetched (stat === null) so it shows a "live" marker; a query
// error surfaces as "ERR" rather than a fake count.
function DataStat({
  locale,
  stat,
  loaded,
}: {
  locale: Locale;
  stat: DataSourceStat | null | undefined;
  loaded: boolean;
}) {
  if (!loaded) return <span className="text-[11px] text-tm-muted">…</span>;
  if (stat === null) return <span className="text-[11px] text-tm-muted">{t(locale, "data.src.live")}</span>;
  if (!stat || stat.rows === null) return <span className="text-[11px] text-tm-warn">ERR</span>;
  const fresh = stat.last_fetched_at ? ago(stat.last_fetched_at, locale) : null;
  return (
    <span className="font-tm-mono text-[11px] tabular-nums text-tm-fg">
      {stat.rows.toLocaleString()}
      {fresh ? <span className="ml-1.5 text-tm-muted">· {fresh}</span> : null}
    </span>
  );
}

// Compact relative age, e.g. "2h" / "3d" / "5m". Null on unparseable input.
function ago(iso: string, locale: Locale): string | null {
  const ms = Date.now() - new Date(iso).getTime();
  if (isNaN(ms) || ms < 0) return null;
  const m = Math.floor(ms / 60000);
  if (m < 60) return locale === "zh" ? `${m}分钟前` : `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return locale === "zh" ? `${h}小时前` : `${h}h`;
  const d = Math.floor(h / 24);
  return locale === "zh" ? `${d}天前` : `${d}d`;
}

function Cell({ children, head = false }: { children: React.ReactNode; head?: boolean }) {
  return (
    <div
      className={
        head
          ? "bg-tm-bg-2 px-3 py-1.5 font-tm-sans text-[11px] font-semibold uppercase tracking-[0.06em] text-tm-muted"
          : "bg-tm-bg px-3 py-2"
      }
    >
      {children}
    </div>
  );
}
