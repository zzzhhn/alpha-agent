"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { FACTOR_EXAMPLES } from "@/components/alpha/FactorExamples";
import { AnalyticsAccordion } from "@/components/alpha/AnalyticsAccordion";
import { EvidencePaneGrid } from "@/components/alpha/EvidencePaneGrid";
import { HypothesisInputCard } from "@/components/alpha/HypothesisInputCard";
import type { InputCardExample, InputCardHistoryEntry } from "@/components/alpha/HypothesisInputCard";
import { useAlphaChain } from "@/components/alpha/useAlphaChain";
import { VerdictBar } from "@/components/alpha/VerdictBar";
import { useToast } from "@/components/ui/toast";
import { addToZoo, isInZoo, removeFromZoo } from "@/lib/factor-zoo";
import { getFavorites, getRecent } from "@/lib/hypothesis-history";
import type { FactorUniverse, HypothesisHistoryEntry } from "@/lib/types";

export default function AlphaPage() {
  const { locale } = useLocale();
  const [text, setText] = useState("");
  const [universe, setUniverse] = useState<FactorUniverse>("SP500");
  const [history, setHistory] = useState<readonly HypothesisHistoryEntry[]>([]);
  const chain = useAlphaChain();
  const { toast } = useToast();

  // History loader: localStorage via getFavorites + getRecent (same as old page lines 114-116).
  // Favorites appear first, then recent non-favorites.
  useEffect(() => {
    const favs = getFavorites();
    const recents = getRecent();
    // Merge: favorites first, then non-duplicate recents
    const seen = new Set(favs.map((e) => e.id));
    const merged = [...favs, ...recents.filter((e) => !seen.has(e.id))];
    setHistory(merged);
  }, []);

  // Map FactorExample (has hypothesisEn/hypothesisZh, name) to InputCardExample (label + text).
  // Locale-aware: zh uses hypothesisZh, en uses hypothesisEn. Mirrors old page line 176.
  const examples = useMemo<ReadonlyArray<InputCardExample>>(
    () =>
      FACTOR_EXAMPLES.map((ex) => ({
        label: ex.name,
        text: locale === "zh" ? ex.hypothesisZh : ex.hypothesisEn,
      })),
    [locale],
  );

  const handleSubmit = useCallback(() => {
    if (text.trim().length === 0) return;
    chain.start(text.trim(), universe);
  }, [text, universe, chain]);

  const handleHistorySelect = useCallback(
    (entry: InputCardHistoryEntry) => {
      setText(entry.request.text);
      if (entry.request.universe) setUniverse(entry.request.universe);
    },
    [],
  );

  const handleReTranslate = useCallback(() => {
    chain.reset();
    // Yield one React tick so the idle state renders before re-submitting.
    setTimeout(() => chain.start(text.trim(), universe), 0);
  }, [chain, text, universe]);

  // translate is available whenever the chain has passed the translate stage.
  const translate =
    chain.state.kind === "backtesting" ||
    chain.state.kind === "backtest_error" ||
    chain.state.kind === "done"
      ? chain.state.translate
      : null;

  const canSave =
    translate !== null && !(translate.smoke.degenerate ?? false);

  // Save-to-Zoo: localStorage via addToZoo (mirrors ZooSaveButton internals).
  // Payload mirrors old page's ZooSaveButton props (lines 276-297):
  //   name, expression, hypothesis, intuition, headlineMetrics (from backtest).
  // Undo is supported because removeFromZoo(id) deletes by id.
  const handleSave = useCallback(async () => {
    if (!translate) return;
    const expression = translate.spec.expression;
    // Guard: don't re-save if already in Zoo; surface a friendly info instead.
    if (isInZoo(expression)) {
      toast.info("Already saved to Zoo");
      return;
    }

    const backtest =
      chain.state.kind === "done" ? chain.state.backtest : null;
    const headlineMetrics = backtest
      ? {
          testSharpe: backtest.test_metrics.sharpe,
          totalReturn:
            backtest.equity_curve.length > 0
              ? backtest.equity_curve[backtest.equity_curve.length - 1].value /
                  backtest.equity_curve[0].value -
                1
              : undefined,
          testIc: backtest.test_metrics.ic_spearman,
        }
      : undefined;

    try {
      const saved = addToZoo({
        name: translate.spec.name,
        expression,
        hypothesis: translate.spec.hypothesis ?? "",
        intuition: translate.spec.justification,
        headlineMetrics,
      });
      toast.success("Saved to Zoo", {
        action: {
          label: "Undo",
          onClick: () => removeFromZoo(saved.id),
        },
      });
    } catch (e) {
      toast.error(`Save failed: ${e instanceof Error ? e.message : String(e)}`);
    }
  }, [translate, chain.state, toast]);

  return (
    <main className="flex flex-col gap-4 p-4">
      <HypothesisInputCard
        text={text}
        onTextChange={setText}
        universe={universe}
        onUniverseChange={setUniverse}
        onSubmit={handleSubmit}
        disabled={chain.isLoading}
        examples={examples}
        history={history as readonly InputCardHistoryEntry[]}
        onHistorySelect={handleHistorySelect}
      />
      <VerdictBar
        state={chain.state}
        metrics={chain.metrics}
        thresholds={chain.thresholds}
        canSave={canSave}
        onSave={handleSave}
        onReTranslate={handleReTranslate}
      />
      <EvidencePaneGrid
        state={chain.state}
        panes={chain.panes}
        onReTranslate={handleReTranslate}
        onRetryBacktest={chain.retryBacktest}
      />
      <AnalyticsAccordion translate={translate} />
    </main>
  );
}
