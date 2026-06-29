"use client";

import { useMemo, useState } from "react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import type { Locale, TranslationKey } from "@/lib/i18n";
import type { FactorExample } from "@/components/alpha/FactorExamples";

/**
 * Grouped, scannable, filterable LIST for FACTOR_EXAMPLES.
 *
 * Supersedes the rejected card grid (FactorExampleCards). Design rationale:
 * a preset picker with structured metadata is best served by a quality-
 * ordered vertical scan, not a gallery of equal-weight cards. Each example
 * is ONE compact line; the verdict tier sections the list so the user reads
 * top-down from the strongest factors to the weakest.
 *
 * Structure:
 *   - search/filter input (name + expression)
 *   - sections ordered Pure Alpha -> Marginal -> Noise (Levered Alpha, if
 *     present, sits with the Pure Alpha tier just after it), each with a
 *     small header + count
 *   - rows: tier dot + name (sans) + inline metrics (mono tabular) +
 *     expression snippet (muted mono). The whole row is the select target.
 *
 * Terminal/Bloomberg aesthetic preserved via tm-* tokens only; mono is used
 * only for numeric content + the expression code; 11px type-scale floor.
 */

// ── Verdict tier ────────────────────────────────────────────────────
// The intuition text leads with a verdict token, e.g.
//   "★ PURE ALPHA tier. …" / "MARGINAL tier (…)." / "NOISE tier …".
// We parse that leading token to drive tier grouping + the row color dot.

type VerdictTier = "pure_alpha" | "levered_alpha" | "marginal" | "noise";

interface VerdictMeta {
  readonly tier: VerdictTier;
  readonly labelKey: TranslationKey;
  // Section header label color + the small per-row color dot.
  readonly dot: string;
  readonly headText: string;
}

const VERDICTS: Record<VerdictTier, VerdictMeta> = {
  pure_alpha: {
    tier: "pure_alpha",
    labelKey: "report.example.verdict.pureAlpha",
    dot: "bg-tm-accent",
    headText: "text-tm-accent",
  },
  levered_alpha: {
    tier: "levered_alpha",
    labelKey: "report.example.verdict.leveredAlpha",
    dot: "bg-tm-accent/60",
    headText: "text-tm-accent",
  },
  marginal: {
    tier: "marginal",
    labelKey: "report.example.verdict.marginal",
    dot: "bg-tm-warn",
    headText: "text-tm-warn",
  },
  noise: {
    tier: "noise",
    labelKey: "report.example.verdict.noise",
    dot: "bg-tm-rule-2",
    headText: "text-tm-muted",
  },
};

// Display order for the sectioned list: strongest verdict first.
const TIER_ORDER: readonly VerdictTier[] = [
  "pure_alpha",
  "levered_alpha",
  "marginal",
  "noise",
];

/** Parse the leading "… tier" token from the intuition string. */
function parseVerdict(intuition: string): VerdictMeta {
  // Only inspect the first clause so trailing prose can't false-match.
  const head = intuition.slice(0, 48).toUpperCase();
  if (head.includes("PURE ALPHA")) return VERDICTS.pure_alpha;
  if (head.includes("LEVERED ALPHA")) return VERDICTS.levered_alpha;
  if (head.includes("MARGINAL")) return VERDICTS.marginal;
  return VERDICTS.noise;
}

/** Stable tier classification for one example (locale-independent). */
export function exampleTier(ex: FactorExample): VerdictTier {
  // Use the EN intuition for classification so the tier never shifts with
  // locale (the verdict token is English in both strings).
  return parseVerdict(ex.intuitionEn).tier;
}

// ── Stat formatting (numbers only — these render in mono tabular) ────

function fmtSharpe(n: number): string {
  return (n >= 0 ? "+" : "") + n.toFixed(2);
}
function fmtIC(n: number): string {
  return (n >= 0 ? "+" : "") + n.toFixed(4);
}
function fmtPct(n: number): string {
  return (n >= 0 ? "+" : "") + (n * 100).toFixed(1) + "%";
}

// ── Single row ──────────────────────────────────────────────────────

interface RowProps {
  readonly example: FactorExample;
  readonly meta: VerdictMeta;
  readonly locale: Locale;
  readonly disabled: boolean;
  readonly selected: boolean;
  readonly onSelect: (e: FactorExample) => void;
}

function FactorExampleRow({
  example,
  meta,
  locale,
  disabled,
  selected,
  onSelect,
}: RowProps) {
  const retPositive = example.totalReturn >= 0;
  const hypothesis = locale === "zh" ? example.hypothesisZh : example.hypothesisEn;
  return (
    <button
      type="button"
      onClick={() => onSelect(example)}
      disabled={disabled}
      title={example.name}
      aria-pressed={selected}
      className={[
        "group flex w-full flex-col gap-1 border-l-2 px-2.5 py-2 text-left transition-colors",
        selected
          ? "border-l-tm-accent bg-tm-accent-soft"
          : "border-l-transparent hover:border-l-tm-rule-2 hover:bg-tm-bg-3",
        "focus-visible:border-l-tm-accent focus-visible:bg-tm-bg-3 focus-visible:outline-none",
        "disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-transparent",
      ].join(" ")}
    >
      {/* Top line: tier dot + name + inline metrics */}
      <span className="flex items-center gap-2.5">
        <span
          className={`h-1.5 w-1.5 shrink-0 rounded-full ${meta.dot}`}
          aria-hidden="true"
        />
        <span className="min-w-0 flex-1 truncate font-tm-sans text-[12px] font-semibold leading-tight text-tm-fg">
          {example.name}
        </span>
        <span className="flex shrink-0 items-baseline gap-x-3">
          <Metric
            label={t(locale, "report.example.stat.sharpe")}
            value={fmtSharpe(example.testSharpe)}
          />
          <Metric
            label={t(locale, "report.example.stat.ic")}
            value={fmtIC(example.testIC)}
          />
          <Metric
            label={t(locale, "report.example.stat.return")}
            value={fmtPct(example.totalReturn)}
            valueClass={retPositive ? "text-tm-pos" : "text-tm-neg"}
          />
        </span>
      </span>

      {/* Expression — the factor's defining code */}
      <code className="block min-w-0 truncate font-tm-mono text-[10.5px] text-tm-accent/90">
        {example.expression}
      </code>

      {/* Hypothesis — the per-row "more info" (locale-aware prose) */}
      <span className="line-clamp-1 font-tm-sans text-[11px] leading-snug text-tm-muted group-hover:text-tm-fg-2">
        {hypothesis}
      </span>
    </button>
  );
}

interface MetricProps {
  readonly label: string;
  readonly value: string;
  readonly valueClass?: string;
}

function Metric({ label, value, valueClass }: MetricProps) {
  return (
    <span className="inline-flex items-baseline gap-1">
      <span className="font-tm-sans text-[10px] uppercase tracking-wide text-tm-muted">
        {label}
      </span>
      <span
        className={`font-tm-mono text-[11px] font-medium tabular-nums ${valueClass ?? "text-tm-fg"}`}
      >
        {value}
      </span>
    </span>
  );
}

// ── Grouped list ────────────────────────────────────────────────────

interface ListProps {
  readonly examples: readonly FactorExample[];
  readonly disabled: boolean;
  /** Name of the currently staged/selected example (highlights its row). */
  readonly selectedName?: string | null;
  readonly onSelect: (e: FactorExample) => void;
}

export function FactorExampleList({
  examples,
  disabled,
  selectedName,
  onSelect,
}: ListProps) {
  const { locale } = useLocale();
  const [query, setQuery] = useState("");

  // Filter by name OR expression (case-insensitive), then group by tier.
  const groups = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = q
      ? examples.filter(
          (e) =>
            e.name.toLowerCase().includes(q) ||
            e.expression.toLowerCase().includes(q),
        )
      : examples;
    return TIER_ORDER.map((tier) => ({
      tier,
      meta: VERDICTS[tier],
      items: filtered.filter((e) => exampleTier(e) === tier),
    })).filter((g) => g.items.length > 0);
  }, [examples, query]);

  const totalShown = groups.reduce((n, g) => n + g.items.length, 0);

  return (
    <div className="flex flex-col gap-2">
      {/* Search / filter */}
      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder={t(locale, "report.example.filterPlaceholder")}
        spellCheck={false}
        className="h-7 w-full border border-tm-rule bg-tm-bg-2 px-2 font-tm-mono text-[11px] text-tm-fg outline-none placeholder:text-tm-muted focus:border-tm-accent"
      />

      {totalShown === 0 ? (
        <p className="px-2 py-3 font-tm-mono text-[11px] text-tm-muted">
          {t(locale, "report.example.filterEmpty")}
        </p>
      ) : (
        <div className="flex flex-col gap-1.5">
          {groups.map((g) => (
            <section key={g.tier}>
              {/* Section header: tier label + count */}
              <div className="flex items-baseline gap-2 border-b border-tm-rule px-2 pb-1">
                <span
                  className={`font-tm-mono text-[10px] font-semibold uppercase tracking-[0.06em] ${g.meta.headText}`}
                >
                  {t(locale, g.meta.labelKey)}
                </span>
                <span className="font-tm-mono text-[10px] tabular-nums text-tm-muted">
                  {g.items.length}
                </span>
              </div>
              {/* Rows */}
              <div className="flex flex-col">
                {g.items.map((example) => (
                  <FactorExampleRow
                    key={example.name}
                    example={example}
                    meta={g.meta}
                    locale={locale}
                    disabled={disabled}
                    selected={example.name === selectedName}
                    onSelect={onSelect}
                  />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
