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

import { useState, type ChangeEvent } from "react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { TmPane } from "@/components/tm/TmPane";
import { TmButton } from "@/components/tm/TmButton";
import { TmChip } from "@/components/tm/TmSubbar";
import {
  FACTOR_EXAMPLES,
  type FactorExample,
} from "@/components/alpha/FactorExamples";
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

        <div className="flex flex-wrap items-center gap-1.5 border-t border-tm-rule pt-2.5">
          <span className="font-tm-mono text-[10px] uppercase tracking-[0.06em] text-tm-muted">
            {t(locale, "signal.form.loadExample")}
          </span>
          {FACTOR_EXAMPLES.map((ex) => (
            <TmChip key={ex.name} onClick={() => loadExample(ex)}>
              {ex.name}
            </TmChip>
          ))}
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
