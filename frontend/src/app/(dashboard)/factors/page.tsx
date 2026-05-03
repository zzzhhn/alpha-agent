"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
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

// Bundle B (T4.1): merge server-backed Factor DB with localStorage Zoo.
// Server is source of truth (every backtest auto-saves); localStorage
// kept as fallback for offline + back-compat with v1 entries that
// haven't been re-run since the migration.
function mergeFactors(server: readonly ServerFactor[], local: readonly ZooEntry[]): readonly ZooEntry[] {
  // Server entries first (always fresher, have run history); local entries
  // appended only if their expression isn't already covered by server.
  const serverExprs = new Set(server.map((f) => f.expression));
  const fromServer: ZooEntry[] = server.map((f) => ({
    id: f.id,
    name: f.name,
    expression: f.expression,
    hypothesis: f.hypothesis ?? "",
    intuition: f.intuition ?? undefined,
    direction: (f.last_direction as ZooEntry["direction"]) ?? "long_short",
    savedAt: f.updated_at ?? f.created_at ?? new Date().toISOString(),
    headlineMetrics: {
      testSharpe: f.last_test_sharpe ?? undefined,
      testIc: f.last_test_ic ?? undefined,
    },
    neutralize: (f.last_neutralize as "none" | "sector" | undefined) ?? undefined,
    benchmarkTicker: (f.last_benchmark as "SPY" | "RSP" | undefined) ?? undefined,
  }));
  return [...fromServer, ...local.filter((e) => !serverExprs.has(e.expression))];
}

export default function FactorsPage() {
  const { locale } = useLocale();
  const router = useRouter();
  const [entries, setEntries] = useState<readonly ZooEntry[]>([]);
  const [decay, setDecay] = useState<readonly DecayAlert[]>([]);

  async function refresh() {
    // Server first (auto-saved); fall back to localStorage if API unreachable
    try {
      const [r1, r2] = await Promise.all([
        listServerFactors(200),
        getDecayAlerts({ min_runs: 3, decay_threshold: 0.5 }),
      ]);
      const local = listZoo();
      if (r1.data) {
        setEntries(mergeFactors(r1.data, local));
      } else {
        setEntries(local);
      }
      if (r2.data) setDecay(r2.data);
    } catch {
      setEntries(listZoo());
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  function loadIntoBacktest(e: ZooEntry) {
    if (typeof window === "undefined") return;
    try {
      // v4 cross-page parity: persist full saved config so /backtest replays
      // the EXACT run that produced the saved metrics (instead of the
      // platform default config). Each field is optional — readConfig fills
      // defaults for v1 entries that predate the schema bump.
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
    refresh();
  }

  /* ── T2.1 cross-correlation panel state ──────────────────────────────── */
  const [corrLoading, setCorrLoading] = useState(false);
  const [corrError, setCorrError] = useState<string | null>(null);
  const [corrResult, setCorrResult] = useState<ZooCorrelationResponse | null>(null);

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
    <div className="flex flex-col gap-4 p-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-text">
            {t(locale, "zoo.title")}
          </h1>
          <p className="mt-1 max-w-3xl text-[14px] leading-relaxed text-muted">
            {t(locale, "zoo.subtitle")}
          </p>
          {decay.length > 0 && (
            <div className="mt-2 inline-block rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-1 text-[12px] text-amber-700 dark:text-amber-400">
              ⚠ {t(locale, "zoo.decayBanner").replace("{n}", String(decay.length))}
              {decay.slice(0, 3).map((d) => (
                <span key={d.factor_id} className="ml-2 font-mono">
                  {d.name}: IC {(d.baseline_ic * 100).toFixed(2)}% → {(d.latest_ic * 100).toFixed(2)}%
                </span>
              ))}
              {decay.length > 3 && <span className="ml-2 text-muted">+{decay.length - 3}</span>}
            </div>
          )}
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={checkCorrelation}
          disabled={corrLoading || entries.length < 2}
          title={
            entries.length < 2
              ? t(locale, "zoo.corr.disabledHint")
              : undefined
          }
        >
          {corrLoading
            ? t(locale, "zoo.corr.running")
            : t(locale, "zoo.corr.run")}
        </Button>
      </header>

      <Card padding="md">
        {entries.length === 0 ? (
          <p className="py-6 text-center text-[14px] text-muted">
            {t(locale, "zoo.empty")}
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead className="bg-[var(--toggle-bg)]">
                <tr>
                  <th className="px-2 py-1.5 text-left font-medium text-muted">{t(locale, "zoo.colName")}</th>
                  <th className="px-2 py-1.5 text-left font-medium text-muted">{t(locale, "zoo.colExpr")}</th>
                  <th className="px-2 py-1.5 text-right font-medium text-muted">{t(locale, "zoo.colSharpe")}</th>
                  <th className="px-2 py-1.5 text-right font-medium text-muted">{t(locale, "zoo.colReturn")}</th>
                  <th className="px-2 py-1.5 text-right font-medium text-muted">{t(locale, "zoo.colIc")}</th>
                  <th className="px-2 py-1.5 text-left font-medium text-muted">{t(locale, "zoo.colSavedAt")}</th>
                  <th className="px-2 py-1.5 text-right font-medium text-muted"></th>
                </tr>
              </thead>
              <tbody>
                {entries.map((e) => (
                  <tr key={e.id} className="border-t border-border">
                    <td className="px-2 py-1.5 font-mono text-text">{e.name}</td>
                    <td className="px-2 py-1.5 max-w-[400px] truncate font-mono text-muted" title={e.expression}>
                      {e.expression}
                    </td>
                    <td className="px-2 py-1.5 text-right font-mono">
                      {e.headlineMetrics?.testSharpe != null
                        ? renderColored(e.headlineMetrics.testSharpe.toFixed(2), e.headlineMetrics.testSharpe)
                        : "—"}
                    </td>
                    <td className="px-2 py-1.5 text-right font-mono">
                      {e.headlineMetrics?.totalReturn != null
                        ? renderColored(`${(e.headlineMetrics.totalReturn * 100).toFixed(1)}%`, e.headlineMetrics.totalReturn)
                        : "—"}
                    </td>
                    <td className="px-2 py-1.5 text-right font-mono">
                      {e.headlineMetrics?.testIc != null
                        ? renderColored(e.headlineMetrics.testIc.toFixed(3), e.headlineMetrics.testIc)
                        : "—"}
                    </td>
                    <td className="px-2 py-1.5 text-muted">
                      {new Date(e.savedAt).toLocaleString(locale === "zh" ? "zh-CN" : "en-US", {
                        month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
                      })}
                    </td>
                    <td className="px-2 py-1.5 text-right">
                      <div className="flex justify-end gap-1">
                        <Button variant="ghost" size="sm" onClick={() => loadIntoBacktest(e)}>
                          {t(locale, "zoo.actLoadBacktest")}
                        </Button>
                        <Button variant="ghost" size="sm" onClick={() => loadIntoReport(e)}>
                          {t(locale, "zoo.actLoadReport")}
                        </Button>
                        <Button variant="ghost" size="sm" onClick={() => loadIntoScreener(e)}>
                          {t(locale, "zoo.actLoadScreener")}
                        </Button>
                        <Button variant="ghost" size="sm" onClick={() => deleteEntry(e.id)}>
                          {t(locale, "zoo.actDelete")}
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {(corrError || corrResult) && (
        <Card padding="md">
          <header className="mb-3">
            <h2 className="text-base font-semibold text-text">
              {t(locale, "zoo.corr.title")}
            </h2>
            {corrResult && (
              <p className="mt-1 text-[13px] text-muted">
                {t(locale, "zoo.corr.subtitle")
                  .replace("{n}", String(corrResult.names.length))
                  .replace("{sessions}", String(corrResult.n_sessions))}
              </p>
            )}
          </header>
          {corrError && <p className="text-[13px] text-red">{corrError}</p>}
          {corrResult && (
            <CorrelationPanel data={corrResult} />
          )}
        </Card>
      )}
    </div>
  );
}

function CorrelationPanel({ data }: { readonly data: ZooCorrelationResponse }) {
  const { locale } = useLocale();
  const { names, matrix, warnings } = data;

  function cellColor(v: number): string {
    if (v >= 0.95) return "bg-red/30 text-red";
    if (v >= 0.8) return "bg-red/15 text-red";
    if (v >= 0.5) return "bg-yellow/15 text-yellow";
    if (v >= -0.5) return "text-muted";
    return "bg-blue/15 text-blue";
  }

  return (
    <div className="flex flex-col gap-3">
      {warnings.length > 0 && (
        <div className="rounded-md border border-red/30 bg-red/5 p-3">
          <div className="mb-2 text-[13px] font-semibold text-red">
            {t(locale, "zoo.corr.warningsHeader")
              .replace("{n}", String(warnings.length))}
          </div>
          <ul className="space-y-1 text-[12px]">
            {warnings.map((w) => (
              <li key={`${w.a}|${w.b}`}>
                <span className="font-mono text-text">{w.a}</span>
                <span className="mx-1 text-muted">↔</span>
                <span className="font-mono text-text">{w.b}</span>
                <span className="ml-2 font-mono text-red">
                  corr = {w.corr >= 0 ? "+" : ""}{w.corr.toFixed(3)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="text-[12px]">
          <thead>
            <tr>
              <th className="px-2 py-1"></th>
              {names.map((n) => (
                <th key={n} className="px-2 py-1 text-left font-mono text-muted">
                  {n}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {matrix.map((row, i) => (
              <tr key={names[i]}>
                <td className="px-2 py-1 font-mono text-muted">{names[i]}</td>
                {row.map((v, j) => (
                  <td
                    key={j}
                    className={`px-2 py-1 text-center font-mono ${cellColor(v)}`}
                  >
                    {v >= 0 ? "+" : ""}{v.toFixed(2)}
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

function renderColored(label: string, value: number) {
  const cls = value > 0 ? "text-green" : value < 0 ? "text-red" : "text-text";
  return <span className={cls}>{label}</span>;
}

