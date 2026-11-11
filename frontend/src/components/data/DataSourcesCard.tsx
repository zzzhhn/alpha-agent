"use client";

import { useLocale } from "@/components/layout/LocaleProvider";
import { t, type Locale } from "@/lib/i18n";
import { TmPane } from "@/components/tm/TmPane";
import { TmTable, TmTableFrame } from "@/components/tm/TmTable";
import { fetchDataSources, type DataSourceStat } from "@/lib/api/data_sources";
import { DataRequestState, useDataRequest } from "./DataControls";
import { useTimezonePreference } from "@/hooks/useTimezonePreference";
import { formatZonedDateTime } from "@/lib/format-datetime";

const SOURCES = [
  { name: "yfinance", key: "yfinance", feeds: "data.src.yf", cadence: "data.cadence.intraday" },
  { name: "FRED", key: "fred", feeds: "data.src.fred", cadence: null },
  { name: "Finnhub", key: "finnhub", feeds: "data.src.finnhub", cadence: "data.cadence.daily" },
  { name: "SEC EDGAR", key: "edgar", feeds: "data.src.edgar", cadence: "data.cadence.daily" },
  { name: "RSS / Yahoo", key: "news", feeds: "data.src.news", cadence: "data.cadence.intraday" },
] as const;

const readSources = async () => ({ data: (await fetchDataSources()).sources, error: null });

export function DataSourcesCard({ version }: { version: number }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const title = zh ? "数据来源" : "Data sources";
  const request = useDataRequest("sources", version, readSources);
  const { timeZone } = useTimezonePreference();

  return (
    <TmPane title={title} meta={zh ? `${SOURCES.length} 个来源` : `${SOURCES.length} sources`}>
      <DataRequestState locale={locale} label={zh ? "来源观测" : "source observations"} request={request} />
      <TmTableFrame><TmTable aria-label={title} density="compact" className="table-fixed text-left">
        <colgroup><col className="w-[18%]" /><col className="w-[30%] sm:w-[37%]" /><col className="w-[20%] sm:w-[16%]" /><col /></colgroup>
        <thead className="bg-tm-bg-2 font-tm-mono text-tm-muted">
          <tr className="border-b border-tm-rule">
            {[zh ? "来源" : "Source", t(locale, "data.src.col_feeds"), zh ? "声明频率" : "Declared cadence", zh ? "存量 / 最近记录" : "Stored / last recorded"]
              .map((label) => <th key={label} scope="col" className="break-words px-2 py-2 font-medium sm:px-3">{label}</th>)}
          </tr>
        </thead>
        <tbody className="divide-y divide-tm-rule">
          {SOURCES.map((source) => (
            <tr key={source.key}>
              <th scope="row" className="break-words px-2 py-2 font-tm-mono font-semibold text-tm-fg sm:px-3">{source.name}</th>
              <td className="break-words px-2 py-2 text-tm-fg-2 sm:px-3">{t(locale, source.feeds)}</td>
              <td className="break-words px-2 py-2 text-tm-muted sm:px-3">{source.cadence ? t(locale, source.cadence) : zh ? "按需拉取" : "On demand"}</td>
              <td className="break-words px-2 py-2 sm:px-3"><Observation stat={request.data?.[source.key]} locale={locale} tickers={source.key === "yfinance"} timeZone={timeZone} /></td>
            </tr>
          ))}
        </tbody>
      </TmTable></TmTableFrame>
    </TmPane>
  );
}

function Observation({ stat, locale, tickers, timeZone }: { stat: DataSourceStat | null | undefined; locale: Locale; tickers: boolean; timeZone: string }) {
  const zh = locale === "zh";
  if (stat === null) return <span className="text-tm-muted">{zh ? "未记录（按需拉取，不入库）" : "Not recorded (fetched on demand, not stored)"}</span>;
  if (stat?.error) return <span className="text-tm-warn">{zh ? "观测不可用" : "Observation unavailable"}</span>;
  if (!stat) return <span className="text-tm-muted">—</span>;
  const timestamp = stat.last_fetched_at ? new Date(stat.last_fetched_at) : null;
  const utc = timestamp && Number.isFinite(timestamp.getTime()) ? timestamp.toISOString() : null;
  const unit = tickers ? (zh ? "只" : "tickers") : zh ? "条" : "rows";
  return (
    <span className="flex flex-wrap items-baseline gap-x-2 font-tm-mono tabular-nums">
      <span className="text-tm-fg">{stat.rows === null ? "—" : `${stat.rows.toLocaleString()} ${unit}`}</span>
      {utc ? <time className="text-tm-muted" dateTime={utc} title={utc}>{formatZonedDateTime(utc, timeZone)} · {timeZone}</time> : <span className="text-tm-muted">—</span>}
    </span>
  );
}
