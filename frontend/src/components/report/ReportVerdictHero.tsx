"use client";

import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { classifyFactorTier } from "@/lib/factor-tier";
import type { ZooEntry } from "@/lib/factor-zoo";
import type { FactorBacktestResponse } from "@/lib/types";

/**
 * ReportVerdictHero (ALPHACORE design, report block lines 553-567) — the
 * decision-first header that sits ABOVE the report picker. It answers, at a
 * glance and before the long tear sheet: which factor is loaded, is it a real
 * factor, and is it worth producing a research report?
 *
 * The right side carries a "switch factor" dropdown of saved Zoo factors:
 * picking one regenerates the whole report for that factor. With nothing
 * loaded yet, the dropdown is the entry point — pick a factor to start.
 *
 * Verdict + recommendation are DERIVED from the loaded backtest's own stats
 * (overfit_flag + classifyFactorTier on α-p / β), never hand-labelled.
 */

type Tone = "pos" | "info" | "warn" | "bad" | "muted";

const TONE_BADGE: Record<Tone, string> = {
  pos: "border-tm-pos text-tm-pos",
  info: "border-tm-accent text-tm-accent",
  warn: "border-tm-warn text-tm-warn",
  bad: "border-tm-neg text-tm-neg",
  muted: "border-tm-rule-2 text-tm-muted",
};

const RECO_GLYPH: Record<Tone, string> = {
  pos: "✓", // ✓
  info: "✓",
  warn: "△", // △
  bad: "✗", // ✗
  muted: "—", // —
};

interface HeroFactor {
  readonly name: string;
  readonly expression: string;
  readonly backtest: FactorBacktestResponse;
}

function deriveReco(bt: FactorBacktestResponse): {
  readonly tone: Tone;
  readonly tierLabel: string;
  readonly recoKey: string;
} {
  const decay = bt.oos_decay;
  const overfit =
    bt.overfit_flag === true ||
    (decay != null && Number.isFinite(decay) && decay > 0.5);
  const tier = classifyFactorTier(bt.alpha_pvalue, bt.beta_market);

  if (overfit) {
    return { tone: "bad", tierLabel: "OVERFIT", recoKey: "report.hero.recoSkip" };
  }
  switch (tier.label) {
    case "PURE ALPHA":
      return { tone: "pos", tierLabel: tier.label, recoKey: "report.hero.recoWorth" };
    case "LEVERED ALPHA":
      return { tone: "info", tierLabel: tier.label, recoKey: "report.hero.recoWorth" };
    case "MARGINAL":
      return { tone: "warn", tierLabel: tier.label, recoKey: "report.hero.recoBorderline" };
    case "NOISE":
      return { tone: "bad", tierLabel: tier.label, recoKey: "report.hero.recoSkip" };
    default:
      return { tone: "muted", tierLabel: "—", recoKey: "report.hero.recoUnknown" };
  }
}

function fmt(v: number | null | undefined, digits: number, signed = false): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return (signed && v >= 0 ? "+" : "") + v.toFixed(digits);
}

export function ReportVerdictHero({
  primary,
  zoo,
  onSwitch,
  running,
}: {
  readonly primary: HeroFactor | null;
  readonly zoo: readonly ZooEntry[];
  readonly onSwitch: (entry: ZooEntry) => void;
  readonly running: boolean;
}) {
  const { locale } = useLocale();
  const tk = (k: string) => t(locale, k as Parameters<typeof t>[1]);

  const reco = primary ? deriveReco(primary.backtest) : null;

  function handleSwitch(e: React.ChangeEvent<HTMLSelectElement>) {
    const entry = zoo.find((z) => z.name === e.target.value);
    if (entry) onSwitch(entry);
  }

  return (
    <section className="flex flex-wrap items-start justify-between gap-4 border border-l-[3px] border-tm-accent bg-tm-accent-soft px-4 py-3.5">
      {/* Left — factor identity + verdict + recommendation */}
      <div className="min-w-0 flex-1">
        {primary && reco ? (
          <>
            <div className="flex flex-wrap items-center gap-2.5">
              <span className="bg-tm-accent px-1.5 py-0.5 font-tm-mono text-[9px] font-bold tracking-[0.16em] text-tm-bg">
                {tk("report.hero.factorTag")}
              </span>
              <span className="font-tm-mono text-base font-bold text-tm-fg">
                {primary.name}
              </span>
              <span
                className={`border px-2 py-px font-tm-mono text-[11px] font-bold tracking-[0.04em] ${TONE_BADGE[reco.tone]}`}
              >
                ★ {reco.tierLabel}
              </span>
            </div>
            <code className="mt-1.5 block break-all font-tm-mono text-[11.5px] text-tm-accent">
              {primary.expression}
            </code>

            {/* Recommendation: is this worth a research report? */}
            <div className="mt-2 flex items-start gap-2">
              <span className={`mt-px font-tm-mono text-sm ${TONE_BADGE[reco.tone].split(" ")[1]}`}>
                {RECO_GLYPH[reco.tone]}
              </span>
              <div className="min-w-0">
                <span className="font-tm-mono text-[9px] font-semibold tracking-[0.14em] text-tm-muted">
                  {tk("report.hero.recoLabel")}
                </span>
                <p className="max-w-3xl text-[13px] leading-snug text-tm-fg">
                  {tk(reco.recoKey)}
                </p>
              </div>
            </div>

            {/* Key numbers */}
            <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 font-tm-mono text-[11.5px] text-tm-muted">
              <span className="inline-flex items-baseline gap-1">
                {tk("report.hero.kpiSharpe")}
                <span className="font-mono tabular-nums text-tm-fg">
                  {fmt(primary.backtest.test_metrics?.sharpe, 2, true)}
                </span>
              </span>
              <span className="inline-flex items-baseline gap-1">
                {tk("report.hero.kpiAlphaP")}
                <span className="font-mono tabular-nums text-tm-fg">
                  {fmt(primary.backtest.alpha_pvalue, 3)}
                </span>
              </span>
              <span className="inline-flex items-baseline gap-1">
                {tk("report.hero.kpiBeta")}
                <span className="font-mono tabular-nums text-tm-fg">
                  {fmt(primary.backtest.beta_market, 2, true)}
                </span>
              </span>
            </div>
          </>
        ) : (
          <div className="flex items-center gap-2">
            <span className="bg-tm-accent px-1.5 py-0.5 font-tm-mono text-[9px] font-bold tracking-[0.16em] text-tm-bg">
              {tk("report.hero.factorTag")}
            </span>
            <p className="text-[13px] leading-snug text-tm-fg-2">
              {tk("report.hero.pickPrompt")}
            </p>
          </div>
        )}
      </div>

      {/* Right — switch-factor dropdown */}
      <label className="flex shrink-0 items-center gap-2 font-tm-mono text-[10px] text-tm-muted">
        {tk("report.hero.switch")}
        <select
          value={primary?.name ?? ""}
          onChange={handleSwitch}
          disabled={running || zoo.length === 0}
          className="cursor-pointer border border-tm-rule bg-tm-bg-3 px-2.5 py-1.5 font-tm-mono text-[12px] text-tm-fg outline-none focus:border-tm-accent disabled:opacity-50"
        >
          <option value="" disabled>
            {tk("report.compare2.pick")}
          </option>
          {zoo.map((z) => (
            <option key={z.id} value={z.name}>
              {z.name}
            </option>
          ))}
        </select>
      </label>
    </section>
  );
}
