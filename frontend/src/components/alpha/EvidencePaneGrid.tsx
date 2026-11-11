"use client";

import type {
  FactorBacktestResponse,
  HypothesisTranslateResponse,
} from "@/lib/types";
import { BacktestPane } from "./BacktestPane";
import { SmokePane } from "./SmokePane";
import { SpecPane } from "./SpecPane";
import { TmStatePane } from "@/components/tm/TmStatePane";
import { useLocale } from "@/components/layout/LocaleProvider";
import type { ChainPaneStates, ChainState } from "./types";

interface Props {
  state: ChainState;
  panes: ChainPaneStates;
  onReTranslate: () => void;
  onRetryBacktest: () => void;
}

function extractTranslate(state: ChainState): HypothesisTranslateResponse | null {
  if (
    state.kind === "backtesting" ||
    state.kind === "backtest_error" ||
    state.kind === "done"
  ) {
    return state.translate;
  }
  return null;
}

function extractBacktest(state: ChainState): FactorBacktestResponse | null {
  return state.kind === "done" ? state.backtest : null;
}

export function EvidencePaneGrid({
  state,
  panes,
  onReTranslate,
  onRetryBacktest,
}: Props) {
  const { locale } = useLocale();
  const translate = extractTranslate(state);
  const backtest = extractBacktest(state);
  const translateError =
    state.kind === "translate_error" ? state.message : null;
  const backtestError =
    state.kind === "backtest_error" ? state.message : null;

  if (state.kind === "idle") {
    return (
      <TmStatePane
        state="empty"
        title={locale === "zh" ? "尚未运行" : "Not run yet"}
        description={locale === "zh" ? "输入假设并翻译后，这里依次显示表达式、冒烟检查与样本外回测。" : "Translate a hypothesis to see its expression, smoke check and out-of-sample backtest here."}
        className="alpha-evidence !min-h-[160px]"
      />
    );
  }

  return (
    <div className="alpha-evidence grid grid-cols-1 gap-3 lg:grid-cols-3">
      <SpecPane
        state={panes.spec}
        data={translate}
        errorMessage={translateError}
        onRetry={onReTranslate}
      />
      <SmokePane
        state={panes.smoke}
        data={translate !== null ? translate.smoke : null}
        backtest={backtest}
        errorMessage={translateError}
      />
      <BacktestPane
        state={panes.backtest}
        data={backtest}
        errorMessage={backtestError}
        onRetry={onRetryBacktest}
      />
    </div>
  );
}
