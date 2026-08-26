"use client";

import { useCallback, useEffect, useState } from "react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { FACTOR_EXAMPLES } from "@/components/alpha/FactorExamples";
import type { FactorExample } from "@/components/alpha/FactorExamples";
import { AnalyticsAccordion } from "@/components/alpha/AnalyticsAccordion";
import { EvidencePaneGrid } from "@/components/alpha/EvidencePaneGrid";
import { HypothesisInputCard } from "@/components/alpha/HypothesisInputCard";
import type { InputCardHistoryEntry } from "@/components/alpha/HypothesisInputCard";
import { useAlphaChain } from "@/components/alpha/useAlphaChain";
import type { AlphaValidationParams } from "@/components/alpha/useAlphaChain";
import { VerdictBar } from "@/components/alpha/VerdictBar";
import { AlphaResearchContext } from "@/components/alpha/AlphaResearchContext";
import { AlphaExperimentLedger } from "@/components/alpha/AlphaExperimentLedger";
import { TmScreen } from "@/components/tm/TmPane";
import { useToast } from "@/components/ui/toast";
import { addToZoo, isInZoo, removeFromZoo } from "@/lib/factor-zoo";
import { getFavorites, getRecent } from "@/lib/hypothesis-history";
import type { FactorUniverse, HypothesisHistoryEntry } from "@/lib/types";

export default function AlphaPage() {
  const { locale } = useLocale();
  const [text, setText] = useState("");
  const [universe, setUniverse] = useState<FactorUniverse>("SP500");
  const [validation, setValidation] = useState<AlphaValidationParams>({
    direction: "long_short",
    topPct: 30,
    transactionCostBps: 10,
    neutralize: "none",
    benchmarkTicker: "SPY",
  });
  const [history, setHistory] = useState<readonly HypothesisHistoryEntry[]>([]);
  const chain = useAlphaChain();
  const { toast } = useToast();

  // History loader: localStorage via getFavorites + getRecent (same as old page lines 114-116).
  // Favorites appear first, then recent non-favorites.
  const reloadHistory = useCallback(() => {
    const favs = getFavorites();
    const recents = getRecent();
    // Merge: favorites first, then non-duplicate recents
    const seen = new Set(favs.map((e) => e.id));
    const merged = [...favs, ...recents.filter((e) => !seen.has(e.id))];
    setHistory(merged);
  }, []);

  useEffect(() => {
    reloadHistory();
    window.addEventListener("alphacore:hypothesis-history", reloadHistory);
    return () => window.removeEventListener("alphacore:hypothesis-history", reloadHistory);
  }, [reloadHistory]);

  // Selecting an example here loads its hypothesis prose into the textarea
  // (the alpha flow translates prose -> expression -> backtest). Locale-aware.
  const handleExampleSelect = useCallback(
    (ex: FactorExample) => {
      setText(locale === "zh" ? ex.hypothesisZh : ex.hypothesisEn);
      setValidation((current) => ({
        ...current,
        direction: ex.direction ?? current.direction,
        topPct: ex.topPct != null ? ex.topPct * 100 : current.topPct,
        transactionCostBps: ex.transactionCostBps ?? current.transactionCostBps,
        neutralize: ex.neutralize ?? current.neutralize,
        benchmarkTicker: ex.benchmarkTicker ?? current.benchmarkTicker,
      }));
    },
    [locale],
  );

  const handleSubmit = useCallback(() => {
    if (text.trim().length === 0) return;
    chain.start(text.trim(), universe, validation);
  }, [text, universe, validation, chain]);

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
    setTimeout(() => chain.start(text.trim(), universe, validation), 0);
  }, [chain, text, universe, validation]);

  // translate is available whenever the chain has passed the translate stage.
  const translate =
    chain.state.kind === "backtesting" ||
    chain.state.kind === "backtest_error" ||
    chain.state.kind === "done"
      ? chain.state.translate
      : null;

  const canSave =
    translate !== null && !(translate.smoke.degenerate ?? false);

  const handleOpenBacktest = useCallback(() => {
    if (!translate || typeof window === "undefined") return;
    window.sessionStorage.setItem("alphacore.backtest.prefill.v1", JSON.stringify({
      name: translate.spec.name,
      expression: translate.spec.expression,
      operators_used: translate.spec.operators_used,
      lookback: translate.spec.lookback,
      hypothesis: translate.spec.hypothesis,
      direction: validation.direction,
      neutralize: validation.neutralize,
      benchmarkTicker: validation.benchmarkTicker,
      mode: "static",
      topPct: validation.topPct / 100,
      bottomPct: validation.topPct / 100,
      transactionCostBps: validation.transactionCostBps,
    }));
    window.location.assign("/backtest");
  }, [translate, validation]);

  // Save-to-Zoo: localStorage via addToZoo (mirrors ZooSaveButton internals).
  // Payload mirrors old page's ZooSaveButton props (lines 276-297):
  //   name, expression, hypothesis, intuition, headlineMetrics (from backtest).
  // Undo is supported because removeFromZoo(id) deletes by id.
  const handleSave = useCallback(async () => {
    if (!translate) return;
    const expression = translate.spec.expression;
    // Guard: don't re-save if already in Zoo; surface a friendly info instead.
    if (isInZoo(expression)) {
      toast.info(t(locale, "alpha.verdict.saveToZoo" as Parameters<typeof t>[1]));
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
      toast.success(t(locale, "alpha.zoo.savedToast" as Parameters<typeof t>[1]), {
        action: {
          label: t(locale, "alpha.zoo.undo" as Parameters<typeof t>[1]),
          onClick: () => removeFromZoo(saved.id),
        },
      });
    } catch (e) {
      toast.error(
        t(locale, "alpha.verdict.saveFailed" as Parameters<typeof t>[1]) +
          (e instanceof Error ? e.message : String(e))
      );
    }
  }, [translate, chain.state, toast, locale]);

  return (
    <TmScreen className="min-h-[calc(100vh-36px)]">
      <AlphaResearchContext state={chain.state} universe={universe} onOpenBacktest={handleOpenBacktest} />
      <HypothesisInputCard
        text={text}
        onTextChange={setText}
        universe={universe}
        onUniverseChange={setUniverse}
        validation={validation}
        onValidationChange={setValidation}
        onSubmit={handleSubmit}
        canRerun={translate !== null}
        onRerun={() => chain.retryBacktest(validation)}
        disabled={chain.isLoading}
        examples={FACTOR_EXAMPLES}
        onExampleSelect={handleExampleSelect}
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
      <section className="border-b border-tm-rule px-6 py-4">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-tm-mono text-[12px] font-semibold tracking-[0.08em] text-tm-fg">
            <span className="mr-2 text-tm-accent">③</span>{locale === "zh" ? "表达式、证据与反证" : "Expression, evidence, and counter-evidence"}
          </h2>
          <span className="text-xs text-tm-muted">{locale === "zh" ? "详细诊断按需展开" : "Detailed diagnostics expand on demand"}</span>
        </div>
        <EvidencePaneGrid
          state={chain.state}
          panes={chain.panes}
          onReTranslate={handleReTranslate}
          onRetryBacktest={() => chain.retryBacktest(validation)}
        />
        <div className="mt-3"><AnalyticsAccordion translate={translate} /></div>
      </section>
      <div className="px-6 py-4">
        <AlphaExperimentLedger history={history} onOpen={handleHistorySelect} />
      </div>
    </TmScreen>
  );
}
