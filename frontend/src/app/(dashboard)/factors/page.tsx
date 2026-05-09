"use client";

/**
 * Factors / Zoo page — workstation port (Stage 3 · 5/9).
 *
 * Merges server-backed Factor DB (auto-saved on every backtest) with
 * localStorage Zoo (offline + v1 back-compat). Layout becomes a
 * dense workstation table:
 *
 *   - TmSubbar: entry counts (server / local / total) + decay pill +
 *     correlation run button
 *   - ZOO.OVERVIEW: 4 KPI cells (entries / decaying / from_server /
 *     from_local)
 *   - DECAY.ALERTS: collapsible listing of factors whose IC has
 *     materially dropped (only shown if alerts exist)
 *   - ZOO.CATALOG: hairline grid table with name / expression /
 *     sharpe / return / IC / saved-at + inline action chips
 *   - CORRELATION (conditional): warnings list + N×N matrix with
 *     red/yellow/blue tone cells
 *
 * Behavior preserved byte-for-byte: server-merge logic, sessionStorage
 * prefill keys for backtest/report/screener, removeFromZoo + refresh.
 */

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useLocale } from "@/components/layout/LocaleProvider";
import { extractOps } from "@/lib/factor-spec";
import { t } from "@/lib/i18n";
import { listZoo, removeFromZoo, type ZooEntry } from "@/lib/factor-zoo";
import {
  runZooCorrelation,
  listServerFactors,
  getDecayAlerts,
  type ServerFactor,
  type DecayAlert,
} from "@/lib/api";
import type { ZooCorrelationResponse } from "@/lib/types";
import { TmScreen, TmPane } from "@/components/tm/TmPane";
import {
  TmSubbar,
  TmSubbarKV,
  TmSubbarSep,
  TmSubbarSpacer,
  TmStatusPill,
} from "@/components/tm/TmSubbar";
import { TmKpi, TmKpiGrid } from "@/components/tm/TmKpi";
import { TmButton } from "@/components/tm/TmButton";

// Bundle B (T4.1): merge server-backed Factor DB with localStorage Zoo.
function mergeFactors(
  server: readonly ServerFactor[],
  local: readonly ZooEntry[],
): readonly ZooEntry[] {
  const serverExprs = new Set(server.map((f) => f.expression));
  const fromServer: ZooEntry[] = server.map((f) => ({
    id: f.id,
    name: f.name,
    expression: f.expression,
    hypothesis: f.hypothesis ?? "",
    intuition: f.intuition ?? undefined,
    direction:
      (f.last_direction as ZooEntry["direction"]) ?? "long_short",
    savedAt: f.updated_at ?? f.created_at ?? new Date().toISOString(),
    headlineMetrics: {
      testSharpe: f.last_test_sharpe ?? undefined,
      testIc: f.last_test_ic ?? undefined,
    },
    neutralize:
      (f.last_neutralize as "none" | "sector" | undefined) ?? undefined,
    benchmarkTicker:
      (f.last_benchmark as "SPY" | "RSP" | undefined) ?? undefined,
  }));
  return [
    ...fromServer,
    ...local.filter((e) => !serverExprs.has(e.expression)),
  ];
}

export default function FactorsPage() {
  const { locale } = useLocale();
  const router = useRouter();
  const [entries, setEntries] = useState<readonly ZooEntry[]>([]);
  const [serverCount, setServerCount] = useState(0);
  const [localCount, setLocalCount] = useState(0);
  const [decay, setDecay] = useState<readonly DecayAlert[]>([]);

  async function refresh() {
    try {
      const [r1, r2] = await Promise.all([
        listServerFactors(200),
        getDecayAlerts({ min_runs: 3, decay_threshold: 0.5 }),
      ]);
      const local = listZoo();
      setLocalCount(local.length);
      if (r1.data) {
        setServerCount(r1.data.length);
        setEntries(mergeFactors(r1.data, local));
      } else {
        setServerCount(0);
        setEntries(local);
      }
      if (r2.data) setDecay(r2.data);
    } catch {
      const local = listZoo();
      setEntries(local);
      setLocalCount(local.length);
      setServerCount(0);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  function loadIntoBacktest(e: ZooEntry) {
    if (typeof window === "undefined") return;
    try {
      window.sessionStorage.setItem(
        "alphacore.backtest.prefill.v1",
        JSON.stringify({
          name: e.name,
          expression: e.expression,
          operators_used: [...extractOps(e.expression)],
          lookback: 12,
          hypothesis: e.hypothesis,
          direction: e.direction,
          neutralize: e.neutralize,
          benchmarkTicker: e.benchmarkTicker,
          mode: e.mode,
          topPct: e.topPct,
          bottomPct: e.bottomPct,
          transactionCostBps: e.transactionCostBps,
        }),
      );
    } catch {
      /* ignore */
    }
    router.push("/backtest");
  }

  function loadIntoReport(e: ZooEntry) {
    if (typeof window === "undefined") return;
    try {
      window.sessionStorage.setItem(
        "alphacore.report.prefill.v1",
        JSON.stringify(e),
      );
    } catch {
      /* ignore */
    }
    router.push("/report");
  }

  function loadIntoScreener(e: ZooEntry) {
    if (typeof window === "undefined") return;
    try {
      window.sessionStorage.setItem(
        "alphacore.screener.prefill.v1",
        JSON.stringify({ ids: [e.id] }),
      );
    } catch {
      /* ignore */
    }
    router.push("/screener");
  }

  function deleteEntry(id: string) {
    removeFromZoo(id);
    void refresh();
  }

  /* ── correlation panel state ─────────────────────────────────── */
  const [corrLoading, setCorrLoading] = useState(false);
  const [corrError, setCorrError] = useState<string | null>(null);
  const [corrResult, setCorrResult] =
    useState<ZooCorrelationResponse | null>(null);

  async function checkCorrelation() {
    if (entries.length < 2) return;
    setCorrLoading(true);
    setCorrError(null);
    setCorrResult(null);
    const res = await runZooCorrelation({
      factors: entries.map((e) => ({
        spec: {
          name: e.name,
          hypothesis: e.hypothesis ?? "",
          expression: e.expression,
          operators_used: [...extractOps(e.expression)],
          lookback: 12,
          universe: "SP500",
          justification: e.intuition ?? e.hypothesis ?? "zoo entry",
        },
        label: e.name,
      })),
    });
    if (res.error || !res.data) {
      setCorrError(res.error ?? "unknown error");
    } else {
      setCorrResult(res.data);
    }
    setCorrLoading(false);
  }

  return (
    <TmScreen>
      <TmSubbar>
        <span className="text-tm-muted">FACTORS · ZOO</span>
        <TmSubbarSep />
        <TmSubbarKV label="ENTRIES" value={entries.length.toString()} />
        <TmSubbarSep />
        <TmSubbarKV label="SERVER" value={serverCount.toString()} />
        <TmSubbarSep />
        <TmSubbarKV label="LOCAL" value={localCount.toString()} />
        <TmSubbarSpacer />
        {decay.length > 0 && (
          <TmStatusPill tone="warn">
            {`${decay.length} DECAYING`}
          </TmStatusPill>
        )}
        {corrLoading && <TmStatusPill tone="warn">RUNNING…</TmStatusPill>}
        <TmButton
          variant="ghost"
          onClick={checkCorrelation}
          disabled={corrLoading || entries.length < 2}
          className="-my-1 px-2"
          title={
            entries.length < 2
              ? t(locale, "zoo.corr.disabledHint")
              : undefined
          }
        >
          {corrLoading
            ? t(locale, "zoo.corr.running")
            : t(locale, "zoo.corr.run")}
        </TmButton>
      </TmSubbar>

      <TmPane
        title="ZOO.OVERVIEW"
        meta={`${entries.length} TOTAL · ${serverCount} SERVER · ${localCount} LOCAL`}
      >
        <TmKpiGrid>
          <TmKpi
            label="ENTRIES"
            value={entries.length.toString()}
            sub="merged"
          />
          <TmKpi
            label="DECAYING"
            value={decay.length.toString()}
            tone={decay.length > 0 ? "warn" : "default"}
            sub="IC drop ≥ 50%"
          />
          <TmKpi
            label="FROM_SERVER"
            value={serverCount.toString()}
            sub="auto-saved"
          />
          <TmKpi
            label="FROM_LOCAL"
            value={localCount.toString()}
            sub="offline-only"
          />
        </TmKpiGrid>
        <p className="border-t border-tm-rule px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
          {t(locale, "zoo.subtitle")}
        </p>
      </TmPane>

      {decay.length > 0 && (
        <TmPane
          title="DECAY.ALERTS"
          meta={`${decay.length} FACTOR${decay.length === 1 ? "" : "S"}`}
        >
          <ul className="flex flex-col">
            {decay.map((d) => (
              <li
                key={d.factor_id}
                className="flex flex-wrap items-center gap-3 border-b border-tm-rule px-3 py-1.5 font-tm-mono text-[11px] last:border-b-0"
              >
                <span className="text-tm-warn">▸</span>
                <span className="text-tm-fg">{d.name}</span>
                <span className="text-tm-muted">IC</span>
                <span className="tabular-nums text-tm-fg-2">
                  {(d.baseline_ic * 100).toFixed(2)}%
                </span>
                <span className="text-tm-muted">→</span>
                <span className="tabular-nums text-tm-neg">
                  {(d.latest_ic * 100).toFixed(2)}%
                </span>
              </li>
            ))}
          </ul>
        </TmPane>
      )}

      <TmPane
        title="ZOO.CATALOG"
        meta={`${entries.length} ENTRIES`}
      >
        {entries.length === 0 ? (
          <p className="px-3 py-6 text-center font-tm-mono text-[11px] text-tm-muted">
            {t(locale, "zoo.empty")}
          </p>
        ) : (
          <div className="overflow-x-auto">
            <div
              className="grid min-w-[1100px] gap-px bg-tm-rule"
              style={{
                gridTemplateColumns:
                  "minmax(140px, 180px) minmax(220px, 1fr) 80px 80px 80px minmax(120px, 140px) minmax(280px, 320px)",
              }}
            >
              <Header>{t(locale, "zoo.colName")}</Header>
              <Header>{t(locale, "zoo.colExpr")}</Header>
              <Header align="right">{t(locale, "zoo.colSharpe")}</Header>
              <Header align="right">{t(locale, "zoo.colReturn")}</Header>
              <Header align="right">{t(locale, "zoo.colIc")}</Header>
              <Header>{t(locale, "zoo.colSavedAt")}</Header>
              <Header align="right">ACTIONS</Header>
              {entries.map((e) => (
                <ZooRow
                  key={e.id}
                  entry={e}
                  locale={locale}
                  onLoadBacktest={() => loadIntoBacktest(e)}
                  onLoadReport={() => loadIntoReport(e)}
                  onLoadScreener={() => loadIntoScreener(e)}
                  onDelete={() => deleteEntry(e.id)}
                />
              ))}
            </div>
          </div>
        )}
      </TmPane>

      {(corrError || corrResult) && (
        <TmPane
          title="CORRELATION"
          meta={
            corrResult
              ? `${corrResult.names.length} FACTORS · ${corrResult.n_sessions} SESSIONS`
              : undefined
          }
        >
          {corrError && (
            <p className="px-3 py-2.5 font-tm-mono text-[11px] text-tm-neg">
              {corrError}
            </p>
          )}
          {corrResult && <CorrelationPanel data={corrResult} />}
        </TmPane>
      )}
    </TmScreen>
  );
}

/* ── Catalog row ──────────────────────────────────────────────────── */

function Header({
  children,
  align = "left",
}: {
  readonly children: React.ReactNode;
  readonly align?: "left" | "right";
}) {
  return (
    <div
      className={`bg-tm-bg-2 px-2 py-1.5 font-tm-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-tm-muted ${
        align === "right" ? "text-right" : ""
      }`}
    >
      {children}
    </div>
  );
}

function ZooRow({
  entry,
  locale,
  onLoadBacktest,
  onLoadReport,
  onLoadScreener,
  onDelete,
}: {
  readonly entry: ZooEntry;
  readonly locale: "zh" | "en";
  readonly onLoadBacktest: () => void;
  readonly onLoadReport: () => void;
  readonly onLoadScreener: () => void;
  readonly onDelete: () => void;
}) {
  const sharpe = entry.headlineMetrics?.testSharpe;
  const totalRet = entry.headlineMetrics?.totalReturn;
  const ic = entry.headlineMetrics?.testIc;
  return (
    <>
      <Cell>
        <span className="text-tm-accent">{entry.name}</span>
      </Cell>
      <Cell title={entry.expression}>
        <span className="block truncate text-tm-fg-2">{entry.expression}</span>
      </Cell>
      <NumCell value={sharpe} format={(v) => v.toFixed(2)} />
      <NumCell
        value={totalRet}
        format={(v) => `${(v * 100).toFixed(1)}%`}
      />
      <NumCell value={ic} format={(v) => v.toFixed(3)} />
      <Cell>
        <span className="text-tm-muted">
          {new Date(entry.savedAt).toLocaleString(
            locale === "zh" ? "zh-CN" : "en-US",
            {
              month: "short",
              day: "numeric",
              hour: "2-digit",
              minute: "2-digit",
            },
          )}
        </span>
      </Cell>
      <Cell align="right">
        <div className="flex justify-end gap-1">
          <TmButton
            variant="ghost"
            onClick={onLoadBacktest}
            className="h-6 px-1.5 text-[10px]"
          >
            {t(locale, "zoo.actLoadBacktest")}
          </TmButton>
          <TmButton
            variant="ghost"
            onClick={onLoadReport}
            className="h-6 px-1.5 text-[10px]"
          >
            {t(locale, "zoo.actLoadReport")}
          </TmButton>
          <TmButton
            variant="ghost"
            onClick={onLoadScreener}
            className="h-6 px-1.5 text-[10px]"
          >
            {t(locale, "zoo.actLoadScreener")}
          </TmButton>
          <TmButton
            variant="ghost"
            onClick={onDelete}
            className="h-6 px-1.5 text-[10px]"
          >
            {t(locale, "zoo.actDelete")}
          </TmButton>
        </div>
      </Cell>
    </>
  );
}

function Cell({
  children,
  align = "left",
  title,
}: {
  readonly children: React.ReactNode;
  readonly align?: "left" | "right";
  readonly title?: string;
}) {
  return (
    <div
      className={`flex min-w-0 items-center bg-tm-bg px-2 py-1 font-tm-mono text-[11px] ${
        align === "right" ? "justify-end" : ""
      }`}
      title={title}
    >
      {children}
    </div>
  );
}

function NumCell({
  value,
  format,
}: {
  readonly value: number | undefined;
  readonly format: (v: number) => string;
}) {
  if (value == null) {
    return (
      <Cell align="right">
        <span className="text-tm-muted">—</span>
      </Cell>
    );
  }
  const tone =
    value > 0 ? "text-tm-pos" : value < 0 ? "text-tm-neg" : "text-tm-fg";
  return (
    <Cell align="right">
      <span className={`tabular-nums ${tone}`}>{format(value)}</span>
    </Cell>
  );
}

/* ── Correlation panel ────────────────────────────────────────────── */

function CorrelationPanel({
  data,
}: {
  readonly data: ZooCorrelationResponse;
}) {
  const { locale } = useLocale();
  const { names, matrix, warnings } = data;

  function cellTone(v: number): string {
    if (v >= 0.95) return "bg-tm-neg-soft text-tm-neg";
    if (v >= 0.8) return "bg-tm-warn-soft text-tm-warn";
    if (v >= 0.5) return "bg-tm-warn-soft text-tm-warn";
    if (v >= -0.5) return "text-tm-fg-2";
    return "bg-tm-accent-soft text-tm-accent";
  }

  return (
    <div className="flex flex-col">
      {warnings.length > 0 && (
        <div className="border-b border-tm-rule bg-tm-bg-2 px-3 py-2.5">
          <div className="mb-1.5 font-tm-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-tm-neg">
            {t(locale, "zoo.corr.warningsHeader").replace(
              "{n}",
              String(warnings.length),
            )}
          </div>
          <ul className="flex flex-col gap-1">
            {warnings.map((w) => (
              <li
                key={`${w.a}|${w.b}`}
                className="flex items-center gap-2 font-tm-mono text-[11px]"
              >
                <span className="text-tm-fg">{w.a}</span>
                <span className="text-tm-muted">↔</span>
                <span className="text-tm-fg">{w.b}</span>
                <span className="ml-2 tabular-nums text-tm-neg">
                  corr = {w.corr >= 0 ? "+" : ""}
                  {w.corr.toFixed(3)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="overflow-x-auto px-3 py-3">
        <table className="font-tm-mono text-[10.5px]">
          <thead>
            <tr>
              <th className="px-2 py-1"></th>
              {names.map((n) => (
                <th
                  key={n}
                  className="whitespace-nowrap px-2 py-1 text-left text-tm-muted"
                >
                  {n}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {matrix.map((row, i) => (
              <tr key={names[i]}>
                <td className="whitespace-nowrap px-2 py-1 text-tm-muted">
                  {names[i]}
                </td>
                {row.map((v, j) => (
                  <td
                    key={j}
                    className={`px-2 py-1 text-center tabular-nums ${cellTone(v)}`}
                  >
                    {v >= 0 ? "+" : ""}
                    {v.toFixed(2)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
