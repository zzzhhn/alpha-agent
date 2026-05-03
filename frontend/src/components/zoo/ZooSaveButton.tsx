"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/Button";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { addToZoo, isInZoo, type ZooDirection } from "@/lib/factor-zoo";

interface ZooSaveButtonProps {
  readonly name: string;
  readonly expression: string;
  readonly hypothesis?: string;
  readonly intuition?: string;
  readonly direction?: ZooDirection;
  readonly headlineMetrics?: {
    readonly testSharpe?: number;
    readonly totalReturn?: number;
    readonly testIc?: number;
  };
  // v4 cross-page parity: persist the full config that produced the
  // saved metrics so replay reproduces the exact backtest, not the
  // platform default.
  readonly neutralize?: "none" | "sector";
  readonly benchmarkTicker?: "SPY" | "RSP";
  readonly mode?: "static" | "walk_forward";
  readonly topPct?: number;
  readonly bottomPct?: number;
  readonly transactionCostBps?: number;
  readonly disabled?: boolean;
}

export function ZooSaveButton({
  name, expression, hypothesis, intuition, direction, headlineMetrics,
  neutralize, benchmarkTicker, mode, topPct, bottomPct, transactionCostBps,
  disabled,
}: ZooSaveButtonProps) {
  const { locale } = useLocale();
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  // Re-check membership whenever the expression changes — a new translate
  // result resets the visual state without forcing the user to refresh.
  useEffect(() => {
    setSaved(isInZoo(expression));
  }, [expression]);

  function save() {
    if (!expression.trim()) return;
    setBusy(true);
    addToZoo({
      name: name.trim() || "user_factor",
      expression: expression.trim(),
      hypothesis: hypothesis ?? "",
      intuition,
      direction,
      headlineMetrics,
      neutralize, benchmarkTicker, mode, topPct, bottomPct, transactionCostBps,
    });
    setSaved(true);
    setBusy(false);
  }

  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={save}
      disabled={disabled || busy || !expression.trim()}
    >
      {saved
        ? t(locale, "zoo.savedBadge")
        : t(locale, "zoo.save")}
    </Button>
  );
}
