"use client";

import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { TmPane } from "@/components/tm/TmPane";

// Live ingest sources. Kept in sync with the signal pipeline: Finnhub (earnings
// -> Catalyst) and SEC EDGAR (Form 4 -> Insider) were added 2026-06; both run
// as daily GitHub-Actions crons that prime the signal cache. `signal` is the
// dimension each source powers (the same codes shown in the attribution radar).
type I18nKey = Parameters<typeof t>[1];

interface SourceRow {
  readonly name: string;
  readonly feedsKey: I18nKey;
  readonly signal: string;
  readonly cadenceKey: I18nKey;
}

const SOURCES: readonly SourceRow[] = [
  { name: "yfinance", feedsKey: "data.src.yf", signal: "Technicals · Analyst · Options", cadenceKey: "data.cadence.intraday" },
  { name: "FRED", feedsKey: "data.src.fred", signal: "Macro", cadenceKey: "data.cadence.daily" },
  { name: "Finnhub", feedsKey: "data.src.finnhub", signal: "Catalyst", cadenceKey: "data.cadence.daily" },
  { name: "SEC EDGAR", feedsKey: "data.src.edgar", signal: "Insider", cadenceKey: "data.cadence.daily" },
  { name: "RSS / Yahoo", feedsKey: "data.src.news", signal: "News", cadenceKey: "data.cadence.intraday" },
];

export function DataSourcesCard() {
  const { locale } = useLocale();
  return (
    <TmPane title="DATA.SOURCES" meta={`${SOURCES.length} PROVIDERS`}>
      <div
        className="grid gap-px bg-tm-rule"
        style={{ gridTemplateColumns: "minmax(110px,140px) 1fr minmax(110px,150px) minmax(90px,110px)" }}
      >
        <Cell head>SOURCE</Cell>
        <Cell head>{t(locale, "data.src.col_feeds")}</Cell>
        <Cell head>SIGNAL</Cell>
        <Cell head>{t(locale, "data.src.col_cadence")}</Cell>
        {SOURCES.map((s) => (
          <Row key={s.name} locale={locale} src={s} />
        ))}
      </div>
    </TmPane>
  );
}

function Row({ locale, src }: { locale: ReturnType<typeof useLocale>["locale"]; src: SourceRow }) {
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
    </>
  );
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
