"use client";

/**
 * TmSignalForm — workstation-style factor signal form.
 *
 * Lays out a textarea for the factor expression + lookback / topN /
 * neutralize controls + factor examples chip strip in a single TmPane.
 * All controls share workstation tokens (tm-bg-2, tm-rule, tm-accent).
 *
 * Slider primitive is inlined here as `TmSlider`: a native range input
 * with workstation-styled thumb + tabular-num value readout. We don't
 * reuse `ui/Slider` because it bakes in legacy Linear-blue tokens.
 */

import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
} from "react";
import { ChevronDown } from "lucide-react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import type { Locale, TranslationKey } from "@/lib/i18n";
import { TmPane } from "@/components/tm/TmPane";
import { TmButton } from "@/components/tm/TmButton";
import { TmChip } from "@/components/tm/TmSubbar";
import {
  FACTOR_EXAMPLES,
  type FactorExample,
} from "@/components/alpha/FactorExamples";
import { exampleTier } from "@/components/alpha/FactorExampleList";
import { extractOps } from "@/lib/factor-spec";

export interface SignalParams {
  readonly expression: string;
  readonly operators_used: readonly string[];
  readonly lookback: number;
  readonly icLookback: number;
  readonly topN: number;
  readonly neutralize: "none" | "sector";
}

interface TmSignalFormProps {
  readonly running: boolean;
  readonly onRun: (p: SignalParams) => void;
}

export function TmSignalForm({ running, onRun }: TmSignalFormProps) {
  const { locale } = useLocale();
  const [expr, setExpr] = useState<string>("rank(ts_mean(returns, 12))");
  const [icLookback, setIcLookback] = useState(60);
  const [topN, setTopN] = useState(10);
  const [neutralize, setNeutralize] = useState<"none" | "sector">("none");

  function loadExample(ex: FactorExample) {
    setExpr(ex.expression);
  }

  function submit() {
    onRun({
      expression: expr.trim(),
      operators_used: [...extractOps(expr)],
      lookback: 12,
      icLookback,
      topN,
      neutralize,
    });
  }

  return (
    <TmPane title="SIGNAL.FORM" meta={`${expr.length} CHARS`}>
      <div className="flex flex-col gap-3 px-3 py-3">
        <textarea
          value={expr}
          onChange={(e) => setExpr(e.target.value)}
          placeholder={t(locale, "signal.form.exprPlaceholder")}
          rows={3}
          spellCheck={false}
          className="w-full resize-none border border-tm-rule bg-tm-bg-2 p-2 font-tm-mono text-[11.5px] leading-relaxed text-tm-fg outline-none transition-colors focus:border-tm-accent"
        />

        <div className="flex flex-wrap items-end gap-4">
          <TmSlider
            label={t(locale, "signal.form.lookback")}
            min={5}
            max={252}
            step={5}
            value={icLookback}
            unit="d"
            onChange={setIcLookback}
            className="min-w-[200px] flex-1"
          />
          <TmSlider
            label={t(locale, "signal.form.topN")}
            min={5}
            max={30}
            step={1}
            value={topN}
            onChange={setTopN}
            className="min-w-[200px] flex-1"
          />
          <NeutralizeChips
            value={neutralize}
            onChange={setNeutralize}
            label={t(locale, "backtest.form.neutralize")}
            hint={t(locale, "backtest.form.neutralizeHint")}
          />
          <TmButton variant="primary" onClick={submit} disabled={running}>
            {running ? "…" : t(locale, "signal.form.run")}
          </TmButton>
        </div>

        {/* Load example — compact grouped dropdown (no flat tile block). */}
        <div className="flex items-center border-t border-tm-rule pt-2.5">
          <LoadExampleMenu disabled={running} onPick={loadExample} />
        </div>
      </div>
    </TmPane>
  );
}

// ── Slider primitive ────────────────────────────────────────────────

interface TmSliderProps {
  readonly label: string;
  readonly value: number;
  readonly min: number;
  readonly max: number;
  readonly step?: number;
  readonly unit?: string;
  readonly onChange: (n: number) => void;
  readonly className?: string;
}

function TmSlider({
  label,
  value,
  min,
  max,
  step = 1,
  unit = "",
  onChange,
  className,
}: TmSliderProps) {
  return (
    <div className={`flex flex-col gap-1 ${className ?? ""}`}>
      <div className="flex items-center justify-between font-tm-mono">
        <label className="text-[10px] font-semibold uppercase tracking-[0.06em] text-tm-muted">
          {label}
        </label>
        <span className="text-[12px] tabular-nums text-tm-fg">
          {value}
          {unit}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e: ChangeEvent<HTMLInputElement>) =>
          onChange(Number(e.target.value))
        }
        className="tm-range h-1 w-full accent-[var(--tm-accent)]"
      />
    </div>
  );
}

// ── Load-example dropdown menu ──────────────────────────────────────
// Replaces the flat chip wrap. A single "Load example ▾" trigger opens a
// grouped popover (sections by verdict tier) so the examples no longer
// occupy a flat tile block in the form.

const TIER_ORDER = ["pure_alpha", "marginal", "noise"] as const;
type Tier = (typeof TIER_ORDER)[number];

const TIER_META: Record<Tier, { readonly labelKey: TranslationKey; readonly dot: string; readonly head: string }> = {
  pure_alpha: {
    labelKey: "report.example.verdict.pureAlpha",
    dot: "bg-tm-accent",
    head: "text-tm-accent",
  },
  marginal: {
    labelKey: "report.example.verdict.marginal",
    dot: "bg-tm-warn",
    head: "text-tm-warn",
  },
  noise: {
    labelKey: "report.example.verdict.noise",
    dot: "bg-tm-rule-2",
    head: "text-tm-muted",
  },
};

// Map the 4-way tier from FactorExampleList onto the 3 sections shown here
// (levered_alpha folds into the pure_alpha section).
function sectionTier(ex: FactorExample): Tier {
  const tier = exampleTier(ex);
  return tier === "levered_alpha" ? "pure_alpha" : tier;
}

function LoadExampleMenu({
  disabled,
  onPick,
}: {
  readonly disabled: boolean;
  readonly onPick: (ex: FactorExample) => void;
}) {
  const { locale } = useLocale();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const groups = useMemo(
    () =>
      TIER_ORDER.map((tier) => ({
        tier,
        meta: TIER_META[tier],
        items: FACTOR_EXAMPLES.filter((ex) => sectionTier(ex) === tier),
      })).filter((g) => g.items.length > 0),
    [],
  );

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        disabled={disabled}
        className="inline-flex items-center gap-1.5 border border-tm-rule bg-tm-bg-2 px-2 py-px font-tm-mono text-[10.5px] leading-4 text-tm-fg-2 transition-colors hover:border-tm-accent hover:text-tm-fg disabled:cursor-not-allowed disabled:opacity-50"
      >
        <span className="uppercase tracking-[0.06em]">
          {t(locale, "signal.form.loadExampleMenu")}
        </span>
        <ChevronDown
          className={`h-3 w-3 transition-transform ${open ? "rotate-180" : ""}`}
          strokeWidth={1.75}
          aria-hidden="true"
        />
      </button>

      {open && (
        <div className="absolute left-0 top-full z-20 mt-1 max-h-[360px] w-[320px] overflow-y-auto border border-tm-rule bg-tm-bg-2 shadow-lg">
          {groups.map((g) => (
            <ExampleMenuSection
              key={g.tier}
              locale={locale}
              labelKey={g.meta.labelKey}
              dot={g.meta.dot}
              head={g.meta.head}
              items={g.items}
              onPick={(ex) => {
                onPick(ex);
                setOpen(false);
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function ExampleMenuSection({
  locale,
  labelKey,
  dot,
  head,
  items,
  onPick,
}: {
  readonly locale: Locale;
  readonly labelKey: TranslationKey;
  readonly dot: string;
  readonly head: string;
  readonly items: readonly FactorExample[];
  readonly onPick: (ex: FactorExample) => void;
}) {
  return (
    <div className="border-b border-tm-rule last:border-b-0">
      <div className="flex items-baseline gap-2 bg-tm-bg-3 px-2 py-1">
        <span
          className={`font-tm-mono text-[10px] font-semibold uppercase tracking-[0.06em] ${head}`}
        >
          {t(locale, labelKey)}
        </span>
        <span className="font-tm-mono text-[10px] tabular-nums text-tm-muted">
          {items.length}
        </span>
      </div>
      <ul>
        {items.map((ex) => (
          <li key={ex.name}>
            <button
              type="button"
              onClick={() => onPick(ex)}
              title={ex.expression}
              className="group flex w-full items-center gap-2 px-2 py-1.5 text-left transition-colors hover:bg-tm-bg-3"
            >
              <span
                className={`h-1.5 w-1.5 shrink-0 rounded-full ${dot}`}
                aria-hidden="true"
              />
              <span className="min-w-0 flex-1 truncate font-tm-sans text-[11.5px] text-tm-fg-2 group-hover:text-tm-fg">
                {ex.name}
              </span>
              <code className="hidden max-w-[140px] shrink-0 truncate font-tm-mono text-[10px] text-tm-muted sm:block">
                {ex.expression}
              </code>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ── Neutralize chip group ───────────────────────────────────────────

function NeutralizeChips({
  value,
  onChange,
  label,
  hint,
}: {
  readonly value: "none" | "sector";
  readonly onChange: (v: "none" | "sector") => void;
  readonly label: string;
  readonly hint: string;
}) {
  const { locale } = useLocale();
  return (
    <div className="flex flex-col gap-1">
      <span className="font-tm-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-tm-muted">
        {label}
      </span>
      <div className="flex items-center gap-1.5">
        {(["none", "sector"] as const).map((m) => (
          <TmChip key={m} on={value === m} onClick={() => onChange(m)}>
            {t(locale, `backtest.form.neutralize.${m}`)}
          </TmChip>
        ))}
        <span className="font-tm-mono text-[10px] text-tm-muted" title={hint}>
          ?
        </span>
      </div>
    </div>
  );
}
