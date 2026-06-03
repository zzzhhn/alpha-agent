"use client";

import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import type { Locale } from "@/lib/i18n";
import type { FactorExample } from "@/components/alpha/FactorExamples";

/**
 * Refined, scannable card grid for FACTOR_EXAMPLES (replaces the flat
 * chip list in REPORT.PICKER). Each card is the click target that loads
 * the example under its validated config (`onSelect`) — identical wiring
 * to the previous TmChip, just a richer presentation.
 *
 * Readability rules honored:
 *   - mono + tabular-nums ONLY for the numeric stat values
 *   - sans for the title, hypothesis prose, and the small stat labels
 *   - 11px type-scale floor (smallest text here is 11px)
 * Terminal/Bloomberg aesthetic preserved via tm-* tokens only.
 */

// ── Verdict tier ────────────────────────────────────────────────────
// The intuition text leads with a verdict token, e.g.
//   "★ PURE ALPHA tier. …"  /  "MARGINAL tier (…)."  /  "NOISE tier …".
// We parse that leading token to drive a colored badge. The data also
// documents a LEVERED ALPHA tier (p<0.05 but |β|≥0.30), handled here.

type VerdictTier = "pure_alpha" | "levered_alpha" | "marginal" | "noise";

interface VerdictMeta {
  readonly tier: VerdictTier;
  readonly labelKey:
    | "report.example.verdict.pureAlpha"
    | "report.example.verdict.leveredAlpha"
    | "report.example.verdict.marginal"
    | "report.example.verdict.noise";
  // Tailwind classes for the badge (text + soft bg + border), tm-token based.
  readonly badge: string;
  // Left rail accent (left border color) so the tier is scannable down
  // the grid edge.
  readonly rail: string;
}

const VERDICTS: Record<VerdictTier, VerdictMeta> = {
  pure_alpha: {
    tier: "pure_alpha",
    labelKey: "report.example.verdict.pureAlpha",
    badge: "border-tm-accent/40 bg-tm-accent-soft text-tm-accent",
    rail: "border-l-tm-accent",
  },
  levered_alpha: {
    tier: "levered_alpha",
    labelKey: "report.example.verdict.leveredAlpha",
    badge: "border-tm-accent/30 bg-tm-accent-soft text-tm-accent",
    rail: "border-l-tm-accent/60",
  },
  marginal: {
    tier: "marginal",
    labelKey: "report.example.verdict.marginal",
    badge: "border-tm-warn/40 bg-tm-warn-soft text-tm-warn",
    rail: "border-l-tm-warn",
  },
  noise: {
    tier: "noise",
    labelKey: "report.example.verdict.noise",
    badge: "border-tm-rule bg-tm-bg-3 text-tm-muted",
    rail: "border-l-tm-rule-2",
  },
};

/** Parse the leading "… tier" token from the intuition string. */
function parseVerdict(intuition: string): VerdictMeta {
  // Take only the first sentence/clause so trailing prose can't false-match.
  const head = intuition.slice(0, 48).toUpperCase();
  if (head.includes("PURE ALPHA")) return VERDICTS.pure_alpha;
  if (head.includes("LEVERED ALPHA")) return VERDICTS.levered_alpha;
  if (head.includes("MARGINAL")) return VERDICTS.marginal;
  return VERDICTS.noise;
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

// ── Single card ─────────────────────────────────────────────────────

interface CardProps {
  readonly example: FactorExample;
  readonly locale: Locale;
  readonly disabled: boolean;
  readonly onSelect: (e: FactorExample) => void;
}

function FactorExampleCard({ example, locale, disabled, onSelect }: CardProps) {
  const verdict = parseVerdict(
    locale === "zh" ? example.intuitionZh : example.intuitionEn,
  );
  const hypothesis =
    locale === "zh" ? example.hypothesisZh : example.hypothesisEn;
  const ret = fmtPct(example.totalReturn);
  const retPositive = example.totalReturn >= 0;

  return (
    <button
      type="button"
      onClick={() => onSelect(example)}
      disabled={disabled}
      title={example.name}
      className={[
        // base card — left tier rail via a 2px colored left border
        "group flex w-full flex-col gap-2.5 overflow-hidden rounded border border-l-2 border-tm-rule bg-tm-bg-2 p-3 text-left",
        verdict.rail,
        // hover affordance (whole card is the load target)
        "transition-colors hover:border-tm-accent hover:bg-tm-bg-3",
        "focus-visible:border-tm-accent focus-visible:outline-none",
        "disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:border-tm-rule disabled:hover:bg-tm-bg-2",
      ].join(" ")}
    >
      {/* Title + verdict badge */}
      <div className="flex items-start justify-between gap-2">
        <span className="font-tm-sans text-[14px] font-semibold leading-snug text-tm-fg">
          {example.name}
        </span>
        <span
          className={`shrink-0 rounded border px-1.5 py-0.5 font-tm-sans text-[11px] font-semibold uppercase tracking-wide ${verdict.badge}`}
        >
          {t(locale, verdict.labelKey)}
        </span>
      </div>

      {/* Compact stat row: SR / IC / total return (numbers = mono tabular) */}
      <dl className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <Stat
          label={t(locale, "report.example.stat.sharpe")}
          value={fmtSharpe(example.testSharpe)}
        />
        <Stat
          label={t(locale, "report.example.stat.ic")}
          value={fmtIC(example.testIC)}
        />
        <Stat
          label={t(locale, "report.example.stat.return")}
          value={ret}
          valueClass={retPositive ? "text-tm-pos" : "text-tm-neg"}
        />
      </dl>

      {/* Hypothesis — secondary sans prose, clamped to 2 lines */}
      <p className="line-clamp-2 font-tm-sans text-[13px] leading-relaxed text-tm-fg-2">
        {hypothesis}
      </p>

      {/* Expression — mono code chip */}
      <code className="block truncate rounded border border-tm-rule bg-tm-bg-3 px-2 py-1 font-tm-mono text-[11px] text-tm-muted group-hover:text-tm-fg-2">
        {example.expression}
      </code>
    </button>
  );
}

interface StatProps {
  readonly label: string;
  readonly value: string;
  readonly valueClass?: string;
}

function Stat({ label, value, valueClass }: StatProps) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="font-tm-sans text-[11px] uppercase tracking-wide text-tm-muted">
        {label}
      </dt>
      <dd
        className={`font-tm-mono text-[13px] font-medium tabular-nums ${valueClass ?? "text-tm-fg"}`}
      >
        {value}
      </dd>
    </div>
  );
}

// ── Grid ────────────────────────────────────────────────────────────

interface GridProps {
  readonly examples: readonly FactorExample[];
  readonly disabled: boolean;
  readonly onSelect: (e: FactorExample) => void;
}

export function FactorExampleCardGrid({
  examples,
  disabled,
  onSelect,
}: GridProps) {
  const { locale } = useLocale();
  return (
    <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
      {examples.map((example) => (
        <FactorExampleCard
          key={example.name}
          example={example}
          locale={locale}
          disabled={disabled}
          onSelect={onSelect}
        />
      ))}
    </div>
  );
}
