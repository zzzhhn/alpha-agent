"use client";

import { useState } from "react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Slider } from "@/components/ui/Slider";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { FACTOR_EXAMPLES, type FactorExample } from "@/components/alpha/FactorExamples";

export interface SignalParams {
  readonly expression: string;
  readonly operators_used: readonly string[];
  readonly lookback: number;
  readonly icLookback: number;
  readonly topN: number;
}

interface SignalFormProps {
  readonly running: boolean;
  readonly onRun: (p: SignalParams) => void;
}

// Naive operator extraction — pulls function-call identifiers out of the
// expression. Backend re-validates via AST, so this only feeds the
// declared-ops list (which the API checks for exact match).
function extractOps(expr: string): string[] {
  const re = /([a-zA-Z_][a-zA-Z0-9_]*)\s*\(/g;
  const set = new Set<string>();
  let m: RegExpExecArray | null;
  while ((m = re.exec(expr))) set.add(m[1]);
  return Array.from(set);
}

export function SignalForm({ running, onRun }: SignalFormProps) {
  const { locale } = useLocale();
  const [expr, setExpr] = useState<string>("rank(ts_mean(returns, 12))");
  const [icLookback, setIcLookback] = useState(60);
  const [topN, setTopN] = useState(10);

  function loadExample(ex: FactorExample) {
    setExpr(ex.expression);
  }

  function submit() {
    onRun({
      expression: expr.trim(),
      operators_used: extractOps(expr),
      lookback: 12,
      icLookback,
      topN,
    });
  }

  return (
    <Card padding="md">
      <header className="mb-3">
        <h2 className="text-base font-semibold text-text">
          {t(locale, "signal.form.title")}
        </h2>
      </header>

      <textarea
        value={expr}
        onChange={(e) => setExpr(e.target.value)}
        placeholder={t(locale, "signal.form.exprPlaceholder")}
        rows={3}
        className="w-full resize-none rounded-md border border-border bg-[var(--toggle-bg)] p-2 font-mono text-sm text-text outline-none focus:border-accent"
      />

      <div className="mt-3 flex flex-wrap items-end gap-4">
        <div className="min-w-[180px] flex-1">
          <Slider
            label={t(locale, "signal.form.lookback")}
            min={5}
            max={252}
            step={5}
            value={icLookback}
            onChange={setIcLookback}
            unit="d"
          />
        </div>
        <div className="min-w-[180px] flex-1">
          <Slider
            label={t(locale, "signal.form.topN")}
            min={5}
            max={30}
            step={1}
            value={topN}
            onChange={setTopN}
          />
        </div>
        <Button onClick={submit} disabled={running}>
          {running ? "…" : t(locale, "signal.form.run")}
        </Button>
      </div>

      <details className="mt-3 border-t border-border pt-2">
        <summary className="cursor-pointer text-[13px] text-muted hover:text-text">
          {t(locale, "signal.form.loadExample")}
        </summary>
        <div className="mt-2 flex flex-wrap gap-1">
          {FACTOR_EXAMPLES.map((ex) => (
            <button
              key={ex.name}
              type="button"
              onClick={() => loadExample(ex)}
              className="rounded bg-[var(--toggle-bg)] px-2 py-1 text-[12px] text-muted hover:text-text"
            >
              {ex.name}
            </button>
          ))}
        </div>
      </details>
    </Card>
  );
}
