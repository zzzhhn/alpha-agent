import { TmScreen, TmPane } from "@/components/tm/TmPane";
import { TmSubbar, TmSubbarKV, TmSubbarSep } from "@/components/tm/TmSubbar";

// Route-level Suspense fallback for /backtest. The real page always renders:
//   TmSubbar (factor / universe / status) ->
//   TmBacktestForm (expression input + config chips + run button, ~h-48) ->
//   USAGE hint pane (one line of muted text, ~h-16).
// Results panes only appear after a run so they are excluded from the skeleton.
export default function BacktestLoading() {
  return (
    <TmScreen>
      <TmSubbar>
        <TmSubbarKV label="BACKTEST" value="—" />
        <TmSubbarSep />
        <TmSubbarKV label="FACTOR" value="—" />
        <TmSubbarSep />
        <TmSubbarKV label="UNIVERSE" value="SP500" />
      </TmSubbar>

      {/* TmBacktestForm — expression textarea + config row + run button */}
      <TmPane title="FACTOR.EXPRESSION" meta="loading...">
        <div className="flex flex-col gap-3 px-3 py-3">
          {/* expression textarea */}
          <div className="h-10 w-full animate-pulse rounded bg-tm-bg-2" />
          {/* config chips row */}
          <div className="flex flex-wrap gap-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <div
                key={i}
                className="h-7 w-24 animate-pulse rounded bg-tm-bg-2"
              />
            ))}
          </div>
          {/* advanced options rows */}
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <div
                key={i}
                className="h-8 w-full animate-pulse rounded bg-tm-bg-2"
              />
            ))}
          </div>
          {/* run button */}
          <div className="flex justify-end">
            <div className="h-8 w-28 animate-pulse rounded bg-tm-bg-2" />
          </div>
        </div>
      </TmPane>

      {/* USAGE hint pane */}
      <TmPane title="USAGE" meta="hint">
        <div className="px-3 py-3">
          <div className="h-4 w-3/4 animate-pulse rounded bg-tm-bg-2" />
        </div>
      </TmPane>
    </TmScreen>
  );
}
