"use client";

import { Fragment, useEffect, useMemo, useState } from "react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Slider } from "@/components/ui/Slider";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { listZoo, readDirection, type ZooEntry, type ZooDirection } from "@/lib/factor-zoo";
import { runScreener } from "@/lib/api";
import type {
  CombineMethod,
  ScreenerFactorInput,
  ScreenerResponse,
} from "@/lib/types";

/** sessionStorage key used by /factors → /screener handoff (D4). Payload
 *  shape: `{ ids: string[] }` — IDs of Zoo entries to pre-select. */
const PREFILL_KEY = "alphacore.screener.prefill.v1";

interface FactorSelection {
  readonly id: string;
  readonly direction: ZooDirection;
  readonly weight: number;
}

export default function ScreenerPage() {
  const { locale } = useLocale();
  const [zoo, setZoo] = useState<readonly ZooEntry[]>([]);
  const [selections, setSelections] = useState<readonly FactorSelection[]>([]);
  const [sectorsInput, setSectorsInput] = useState("");
  const [excludeInput, setExcludeInput] = useState("");
  const [minCap, setMinCap] = useState("");
  const [maxCap, setMaxCap] = useState("");
  const [lookback, setLookback] = useState(60);
  const [topN, setTopN] = useState(20);
  const [combineMethod, setCombineMethod] = useState<CombineMethod>("equal_z");
  const [asOfDate, setAsOfDate] = useState("");
  const [neutralize, setNeutralize] = useState<"none" | "sector">("none");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ScreenerResponse | null>(null);
  const [expandedTicker, setExpandedTicker] = useState<string | null>(null);

  // Initial Zoo load + handoff prefill from /factors page.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const entries = listZoo();
    setZoo(entries);

    let preselectIds: string[] = [];
    try {
      const raw = window.sessionStorage.getItem(PREFILL_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as { ids?: string[] };
        preselectIds = Array.isArray(parsed.ids) ? parsed.ids : [];
        window.sessionStorage.removeItem(PREFILL_KEY);
      }
    } catch {
      /* malformed prefill — ignore */
    }

    const validPreselect = preselectIds
      .filter((id) => entries.some((e) => e.id === id))
      .map<FactorSelection>((id) => {
        const e = entries.find((x) => x.id === id)!;
        return { id, direction: readDirection(e), weight: 1.0 };
      });
    setSelections(validPreselect);
  }, []);

  const selectedById = useMemo(() => {
    const m = new Map<string, FactorSelection>();
    for (const s of selections) m.set(s.id, s);
    return m;
  }, [selections]);

  function toggleFactor(entry: ZooEntry) {
    if (selectedById.has(entry.id)) {
      setSelections((prev) => prev.filter((s) => s.id !== entry.id));
    } else {
      setSelections((prev) => [
        ...prev,
        { id: entry.id, direction: readDirection(entry), weight: 1.0 },
      ]);
    }
  }

  function updateSelection(id: string, patch: Partial<FactorSelection>) {
    setSelections((prev) =>
      prev.map((s) => (s.id === id ? { ...s, ...patch } : s)),
    );
  }

  async function run() {
    if (selections.length === 0) {
      setError(t(locale, "screener.factors.empty"));
      return;
    }
    setRunning(true);
    setError(null);

    const factors: ScreenerFactorInput[] = selections.map((sel) => {
      const entry = zoo.find((e) => e.id === sel.id)!;
      return {
        spec: {
          name: entry.name,
          hypothesis: entry.hypothesis ?? "",
          expression: entry.expression,
          operators_used: extractOps(entry.expression),
          lookback: 12,
          universe: "SP500",
          justification: entry.intuition ?? entry.hypothesis ?? "screener factor",
        },
        direction: sel.direction,
        weight: sel.weight,
      };
    });

    const sectors = sectorsInput
      .split(/[,，\s]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    const exclude = excludeInput
      .split(/[,，\s]+/)
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean);

    const res = await runScreener({
      factors,
      universe_filter: {
        sectors: sectors.length > 0 ? sectors : undefined,
        min_cap: minCap.trim() ? Number(minCap) : undefined,
        max_cap: maxCap.trim() ? Number(maxCap) : undefined,
        exclude_tickers: exclude.length > 0 ? exclude : undefined,
      },
      lookback_days: lookback,
      top_n: topN,
      combine_method: combineMethod,
      as_of_date: asOfDate.trim() || null,
      neutralize,
    });

    if (res.error || !res.data) {
      setError(res.error ?? "unknown error");
    } else {
      setResult(res.data);
    }
    setRunning(false);
  }

  function exportCsv() {
    if (!result) return;
    const headers = [
      "rank", "ticker", "sector", "cap", "composite",
      ...result.factor_diagnostics.map((d, i) => `factor${i}_z`),
    ];
    const rows = result.recommendations.map((r) => [
      String(r.rank),
      r.ticker,
      r.sector ?? "",
      r.cap != null ? r.cap.toFixed(0) : "",
      r.composite_score.toFixed(4),
      ...r.per_factor_scores.map((p) => p.z.toFixed(4)),
    ]);
    const csv = [headers, ...rows]
      .map((row) => row.map((c) => `"${c.replace(/"/g, '""')}"`).join(","))
      .join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `screener_${result.metadata.as_of_date}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="flex flex-col gap-4 p-6">
      <header>
        <h1 className="text-2xl font-semibold text-text">
          {t(locale, "screener.title")}
        </h1>
        <p className="mt-1 max-w-3xl text-[14px] leading-relaxed text-muted">
          {t(locale, "screener.subtitle")}
        </p>
      </header>

      <FactorPickerCard
        zoo={zoo}
        selectedById={selectedById}
        onToggle={toggleFactor}
        onUpdate={updateSelection}
        showWeights={combineMethod === "user_weighted"}
      />

      <UniverseFilterCard
        sectorsInput={sectorsInput}
        onSectors={setSectorsInput}
        excludeInput={excludeInput}
        onExclude={setExcludeInput}
        minCap={minCap}
        onMinCap={setMinCap}
        maxCap={maxCap}
        onMaxCap={setMaxCap}
      />

      <CombineParamsCard
        lookback={lookback}
        onLookback={setLookback}
        topN={topN}
        onTopN={setTopN}
        combineMethod={combineMethod}
        onCombineMethod={setCombineMethod}
        asOfDate={asOfDate}
        onAsOfDate={setAsOfDate}
      />

      <Card padding="md">
        <div className="flex items-center gap-2 text-[13px] text-muted">
          <span>{t(locale, "backtest.form.neutralize")}:</span>
          {(["none", "sector"] as const).map((mode) => (
            <button
              key={mode}
              type="button"
              onClick={() => setNeutralize(mode)}
              className={`rounded px-2 py-0.5 text-[12px] ${
                neutralize === mode
                  ? "bg-accent text-white"
                  : "bg-[var(--toggle-bg)] text-muted hover:text-text"
              }`}
            >
              {t(locale, `backtest.form.neutralize.${mode}`)}
            </button>
          ))}
          <span className="text-[12px] text-muted">
            {t(locale, "backtest.form.neutralizeHint")}
          </span>
        </div>
      </Card>

      <div className="flex justify-end">
        <Button onClick={run} disabled={running || selections.length === 0}>
          {running ? t(locale, "screener.running") : t(locale, "screener.run")}
        </Button>
      </div>

      {error && (
        <Card padding="md">
          <p className="text-base text-red">
            {t(locale, "screener.error")}: {error}
          </p>
        </Card>
      )}

      {result && (
        <div className="flex flex-wrap gap-2">
          {result.metadata.survivorship_corrected ? (
            <span className="inline-block rounded-md border border-green/40 bg-green/10 px-2 py-0.5 text-[11px] text-green">
              {t(locale, "backtest.kpi.survivorshipCorrected").replace(
                "{date}", String(result.metadata.membership_as_of ?? "—"),
              )}
            </span>
          ) : (
            <span className="inline-block rounded-md border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-[11px] text-amber-600 dark:text-amber-400">
              {t(locale, "backtest.kpi.survivorshipLegacy")}
            </span>
          )}
          {result.metadata.neutralize === "sector" && (
            <span className="inline-block rounded-md border border-accent/40 bg-accent/10 px-2 py-0.5 text-[11px] text-accent">
              ✓ {t(locale, "backtest.form.neutralize.sector")}
            </span>
          )}
        </div>
      )}

      {result && (
        <ResultsCard
          result={result}
          expandedTicker={expandedTicker}
          onExpand={setExpandedTicker}
          onExport={exportCsv}
        />
      )}

      {result && result.factor_diagnostics.length > 0 && (
        <DiagnosticsCard diagnostics={result.factor_diagnostics} />
      )}
    </div>
  );
}

/* ── Subcomponents ─────────────────────────────────────────────────────── */

function FactorPickerCard({
  zoo, selectedById, onToggle, onUpdate, showWeights,
}: {
  readonly zoo: readonly ZooEntry[];
  readonly selectedById: Map<string, FactorSelection>;
  readonly onToggle: (e: ZooEntry) => void;
  readonly onUpdate: (id: string, patch: Partial<FactorSelection>) => void;
  readonly showWeights: boolean;
}) {
  const { locale } = useLocale();

  return (
    <Card padding="md">
      <header className="mb-3">
        <h2 className="text-base font-semibold text-text">
          {t(locale, "screener.factors.title")}
        </h2>
        <p className="mt-1 text-[13px] leading-relaxed text-muted">
          {t(locale, "screener.factors.subtitle")}
        </p>
      </header>

      {zoo.length === 0 ? (
        <p className="py-6 text-center text-[14px] text-muted">
          {t(locale, "screener.factors.empty")}
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-[13px]">
            <thead className="bg-[var(--toggle-bg)]">
              <tr>
                <th className="w-10 px-2 py-1.5"></th>
                <th className="px-2 py-1.5 text-left font-medium text-muted">
                  {t(locale, "screener.factors.colName")}
                </th>
                <th className="px-2 py-1.5 text-left font-medium text-muted">
                  {t(locale, "screener.factors.colDirection")}
                </th>
                {showWeights && (
                  <th className="px-2 py-1.5 text-right font-medium text-muted">
                    {t(locale, "screener.factors.colWeight")}
                  </th>
                )}
              </tr>
            </thead>
            <tbody>
              {zoo.map((e) => {
                const sel = selectedById.get(e.id);
                return (
                  <tr key={e.id} className="border-t border-border">
                    <td className="px-2 py-1.5 text-center">
                      <input
                        type="checkbox"
                        checked={Boolean(sel)}
                        onChange={() => onToggle(e)}
                        className="cursor-pointer"
                      />
                    </td>
                    <td className="px-2 py-1.5">
                      <div className="font-mono text-text">{e.name}</div>
                      <div className="font-mono text-[12px] text-muted truncate max-w-[400px]" title={e.expression}>
                        {e.expression}
                      </div>
                    </td>
                    <td className="px-2 py-1.5">
                      {sel ? (
                        <select
                          value={sel.direction}
                          onChange={(ev) => onUpdate(e.id, { direction: ev.target.value as ZooDirection })}
                          className="rounded border border-border bg-[var(--toggle-bg)] px-2 py-1 text-[12px] text-text"
                        >
                          <option value="long_short">long_short</option>
                          <option value="long_only">long_only</option>
                          <option value="short_only">short_only</option>
                        </select>
                      ) : (
                        <span className="text-muted">—</span>
                      )}
                    </td>
                    {showWeights && (
                      <td className="px-2 py-1.5 text-right">
                        {sel ? (
                          <input
                            type="number"
                            min={0}
                            max={10}
                            step={0.1}
                            value={sel.weight}
                            onChange={(ev) => onUpdate(e.id, { weight: Number(ev.target.value) })}
                            className="w-20 rounded border border-border bg-[var(--toggle-bg)] px-2 py-1 text-right font-mono text-text"
                          />
                        ) : (
                          <span className="text-muted">—</span>
                        )}
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

function UniverseFilterCard({
  sectorsInput, onSectors, excludeInput, onExclude, minCap, onMinCap, maxCap, onMaxCap,
}: {
  readonly sectorsInput: string;
  readonly onSectors: (v: string) => void;
  readonly excludeInput: string;
  readonly onExclude: (v: string) => void;
  readonly minCap: string;
  readonly onMinCap: (v: string) => void;
  readonly maxCap: string;
  readonly onMaxCap: (v: string) => void;
}) {
  const { locale } = useLocale();
  return (
    <Card padding="md">
      <header className="mb-3">
        <h2 className="text-base font-semibold text-text">
          {t(locale, "screener.universe.title")}
        </h2>
      </header>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <LabelledInput
          label={t(locale, "screener.universe.sectors")}
          value={sectorsInput}
          onChange={onSectors}
          placeholder="Technology, Healthcare"
        />
        <LabelledInput
          label={t(locale, "screener.universe.exclude")}
          value={excludeInput}
          onChange={onExclude}
          placeholder="TSLA, NVDA"
        />
        <LabelledInput
          label={t(locale, "screener.universe.minCap")}
          value={minCap}
          onChange={onMinCap}
          placeholder="10000000000"
          numeric
        />
        <LabelledInput
          label={t(locale, "screener.universe.maxCap")}
          value={maxCap}
          onChange={onMaxCap}
          placeholder="3000000000000"
          numeric
        />
      </div>
    </Card>
  );
}

function CombineParamsCard({
  lookback, onLookback, topN, onTopN, combineMethod, onCombineMethod, asOfDate, onAsOfDate,
}: {
  readonly lookback: number;
  readonly onLookback: (v: number) => void;
  readonly topN: number;
  readonly onTopN: (v: number) => void;
  readonly combineMethod: CombineMethod;
  readonly onCombineMethod: (v: CombineMethod) => void;
  readonly asOfDate: string;
  readonly onAsOfDate: (v: string) => void;
}) {
  const { locale } = useLocale();
  const methods: readonly { value: CombineMethod; labelKey: string }[] = [
    { value: "equal_z", labelKey: "screener.params.combineEqualZ" },
    { value: "ic_weighted", labelKey: "screener.params.combineIcWeighted" },
    { value: "user_weighted", labelKey: "screener.params.combineUserWeighted" },
  ];
  return (
    <Card padding="md">
      <header className="mb-3">
        <h2 className="text-base font-semibold text-text">
          {t(locale, "screener.params.title")}
        </h2>
      </header>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <Slider
          label={t(locale, "screener.params.lookback")}
          min={10} max={252} step={10}
          value={lookback} onChange={onLookback} unit="d"
        />
        <Slider
          label={t(locale, "screener.params.topN")}
          min={5} max={100} step={5}
          value={topN} onChange={onTopN} unit=""
        />
        <div>
          <label className="mb-1 block text-[13px] text-muted">
            {t(locale, "screener.params.combine")}
          </label>
          <div className="flex flex-wrap gap-2">
            {methods.map((m) => (
              <button
                key={m.value}
                type="button"
                onClick={() => onCombineMethod(m.value)}
                className={
                  combineMethod === m.value
                    ? "rounded-md bg-accent/15 px-2 py-1 text-[12px] text-accent"
                    : "rounded-md px-2 py-1 text-[12px] text-muted hover:bg-[var(--toggle-bg)] hover:text-text"
                }
              >
                {t(locale, m.labelKey as Parameters<typeof t>[1])}
              </button>
            ))}
          </div>
        </div>
        <LabelledInput
          label={t(locale, "screener.params.asOf")}
          value={asOfDate}
          onChange={onAsOfDate}
          placeholder="YYYY-MM-DD"
        />
      </div>
    </Card>
  );
}

function ResultsCard({
  result, expandedTicker, onExpand, onExport,
}: {
  readonly result: ScreenerResponse;
  readonly expandedTicker: string | null;
  readonly onExpand: (t: string | null) => void;
  readonly onExport: () => void;
}) {
  const { locale } = useLocale();
  const recs = result.recommendations;
  const subtitle = t(locale, "screener.results.subtitle").replace("{n}", String(recs.length));

  return (
    <Card padding="md">
      <header className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-text">
            {t(locale, "screener.results.title")}
          </h2>
          <p className="mt-1 text-[13px] leading-relaxed text-muted">
            {subtitle}
          </p>
        </div>
        <Button variant="ghost" size="sm" onClick={onExport}>
          {t(locale, "screener.results.exportCsv")}
        </Button>
      </header>

      {recs.length === 0 ? (
        <p className="py-6 text-center text-[14px] text-muted">
          {t(locale, "screener.results.empty")}
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-[13px]">
            <thead className="bg-[var(--toggle-bg)]">
              <tr>
                <th className="px-2 py-1.5 text-left font-medium text-muted">{t(locale, "screener.results.colRank")}</th>
                <th className="px-2 py-1.5 text-left font-medium text-muted">{t(locale, "screener.results.colTicker")}</th>
                <th className="px-2 py-1.5 text-left font-medium text-muted">{t(locale, "screener.results.colSector")}</th>
                <th className="px-2 py-1.5 text-right font-medium text-muted">{t(locale, "screener.results.colCap")}</th>
                <th className="px-2 py-1.5 text-right font-medium text-muted">{t(locale, "screener.results.colComposite")}</th>
                <th className="w-8 px-2 py-1.5"></th>
              </tr>
            </thead>
            <tbody>
              {recs.map((r) => {
                const isOpen = expandedTicker === r.ticker;
                return (
                  <Fragment key={r.ticker}>
                    <tr className="border-t border-border">
                      <td className="px-2 py-1.5 font-mono text-muted">{r.rank}</td>
                      <td className="px-2 py-1.5 font-mono font-semibold text-text">{r.ticker}</td>
                      <td className="px-2 py-1.5 text-text">{r.sector ?? "—"}</td>
                      <td className="px-2 py-1.5 text-right font-mono text-muted">
                        {r.cap != null ? formatCap(r.cap) : "—"}
                      </td>
                      <td className="px-2 py-1.5 text-right font-mono text-text">
                        {r.composite_score.toFixed(3)}
                      </td>
                      <td className="px-2 py-1.5 text-center">
                        <button
                          type="button"
                          onClick={() => onExpand(isOpen ? null : r.ticker)}
                          className="text-muted hover:text-text"
                        >
                          {isOpen ? "▾" : "▸"}
                        </button>
                      </td>
                    </tr>
                    {isOpen && (
                      <tr className="border-t border-border bg-[var(--toggle-bg)]">
                        <td colSpan={6} className="px-4 py-3">
                          <ContributionBars
                            scores={r.per_factor_scores}
                            diagnostics={result.factor_diagnostics}
                          />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

function ContributionBars({
  scores, diagnostics,
}: {
  readonly scores: ScreenerResponse["recommendations"][number]["per_factor_scores"];
  readonly diagnostics: ScreenerResponse["factor_diagnostics"];
}) {
  const max = Math.max(0.1, ...scores.map((s) => Math.abs(s.contribution)));
  return (
    <div className="space-y-1">
      {scores.map((s) => {
        const diag = diagnostics[s.factor_idx];
        const pct = (Math.abs(s.contribution) / max) * 100;
        const positive = s.contribution >= 0;
        return (
          <div key={s.factor_idx} className="flex items-center gap-3 text-[12px]">
            <code className="w-48 truncate font-mono text-text" title={diag?.expression ?? ""}>
              {diag?.expression ?? `factor[${s.factor_idx}]`}
            </code>
            <div className="relative flex h-4 flex-1 items-center">
              <div className="absolute left-1/2 h-full w-px bg-border" />
              <div
                className="absolute h-full"
                style={{
                  [positive ? "left" : "right"]: "50%",
                  width: `${pct / 2}%`,
                  background: positive ? "#22c55e" : "#ef4444",
                }}
              />
            </div>
            <span className="w-16 text-right font-mono text-text">
              {s.contribution >= 0 ? "+" : ""}{s.contribution.toFixed(3)}
            </span>
            <span className="w-14 text-right font-mono text-muted">
              z={s.z.toFixed(2)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function DiagnosticsCard({
  diagnostics,
}: {
  readonly diagnostics: ScreenerResponse["factor_diagnostics"];
}) {
  const { locale } = useLocale();
  return (
    <Card padding="md">
      <header className="mb-3">
        <h2 className="text-base font-semibold text-text">
          {t(locale, "screener.diagnostics.title")}
        </h2>
      </header>
      <div className="overflow-x-auto">
        <table className="w-full text-[13px]">
          <thead className="bg-[var(--toggle-bg)]">
            <tr>
              <th className="px-2 py-1.5 text-left font-medium text-muted">{t(locale, "screener.diagnostics.colExpr")}</th>
              <th className="px-2 py-1.5 text-right font-medium text-muted">{t(locale, "screener.diagnostics.colIc")}</th>
              <th className="px-2 py-1.5 text-right font-medium text-muted">{t(locale, "screener.diagnostics.colWeight")}</th>
              <th className="px-2 py-1.5 text-right font-medium text-muted">{t(locale, "screener.diagnostics.colEligible")}</th>
            </tr>
          </thead>
          <tbody>
            {diagnostics.map((d) => (
              <tr key={d.factor_idx} className="border-t border-border">
                <td className="px-2 py-1.5 font-mono text-text" title={d.expression}>
                  <span className="block max-w-[400px] truncate">{d.expression}</span>
                </td>
                <td className="px-2 py-1.5 text-right font-mono">
                  {colored(d.in_window_ic.toFixed(3), d.in_window_ic)}
                </td>
                <td className="px-2 py-1.5 text-right font-mono text-text">
                  {(d.used_weight * 100).toFixed(1)}%
                </td>
                <td className="px-2 py-1.5 text-right font-mono text-muted">
                  {d.n_eligible}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

/* ── Helpers ───────────────────────────────────────────────────────────── */

function LabelledInput({
  label, value, onChange, placeholder, numeric,
}: {
  readonly label: string;
  readonly value: string;
  readonly onChange: (v: string) => void;
  readonly placeholder?: string;
  readonly numeric?: boolean;
}) {
  return (
    <div>
      <label className="mb-1 block text-[13px] text-muted">{label}</label>
      <input
        type={numeric ? "number" : "text"}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded border border-border bg-[var(--toggle-bg)] px-2 py-1 text-[13px] text-text outline-none focus:border-accent"
      />
    </div>
  );
}

function colored(label: string, value: number) {
  const cls = value > 0 ? "text-green" : value < 0 ? "text-red" : "text-text";
  return <span className={cls}>{label}</span>;
}

function formatCap(cap: number): string {
  if (cap >= 1e12) return `${(cap / 1e12).toFixed(2)}T`;
  if (cap >= 1e9) return `${(cap / 1e9).toFixed(1)}B`;
  if (cap >= 1e6) return `${(cap / 1e6).toFixed(0)}M`;
  return cap.toFixed(0);
}

function extractOps(expr: string): string[] {
  const re = /([a-zA-Z_][a-zA-Z0-9_]*)\s*\(/g;
  const set = new Set<string>();
  let m: RegExpExecArray | null;
  while ((m = re.exec(expr))) set.add(m[1]);
  return Array.from(set);
}
