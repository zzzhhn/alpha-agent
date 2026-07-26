"use client";

// PaperOverviewPane — account KPIs (Metric strip, no card shell) + positions
// table + reset control. Migrated out of the old PaperTab; the trade form
// moved to its own tab (PaperTradePane) per the redesign spec.
import type { AccountResponse } from "@/lib/api/paper";
import { resetAccount } from "@/lib/api/paper";
import SimPositionRow from "../SimPositionRow";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t, type Locale } from "@/lib/i18n";
import { TmButton } from "@/components/tm/TmButton";
import { Metric, Disclaimer, TwoStepConfirm } from "./PaperUi";

const FMT = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const PCT = (n: number) => `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;

const POS_HEADERS: Record<Locale, string[]> = {
  zh: ["代码", "数量", "均价", "现价", "盈亏", "盈亏%"],
  en: ["Ticker", "Qty", "Avg Cost", "Price", "PnL", "PnL%"],
};

export default function PaperOverviewPane({
  account,
  onReset,
  onGoToTrade,
}: {
  readonly account: AccountResponse;
  readonly onReset: () => Promise<void>;
  readonly onGoToTrade: () => void;
}) {
  const { locale } = useLocale();

  async function handleReset() {
    await resetAccount();
    await onReset();
  }

  return (
    <div className="flex flex-col gap-4 px-3 py-3">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Metric
          label={t(locale, "sim.account.nav")}
          value={`$${FMT.format(account.portfolio_value)}`}
          tone={account.total_return_pct >= 0 ? "text-tm-pos" : "text-tm-neg"}
        />
        <Metric label={t(locale, "sim.account.cash")} value={`$${FMT.format(account.cash)}`} />
        <Metric
          label={t(locale, "sim.account.unrealized")}
          value={`${account.unrealized_pnl >= 0 ? "+" : ""}$${FMT.format(Math.abs(account.unrealized_pnl))}`}
          tone={account.unrealized_pnl >= 0 ? "text-tm-pos" : "text-tm-neg"}
        />
        <Metric
          label={t(locale, "sim.account.realized")}
          value={`${account.realized_pnl >= 0 ? "+" : ""}$${FMT.format(Math.abs(account.realized_pnl))}`}
          tone={account.realized_pnl >= 0 ? "text-tm-pos" : "text-tm-neg"}
        />
      </div>
      <p className="font-tm-mono text-[10px] tabular-nums text-tm-muted">
        {PCT(account.total_return_pct)}
      </p>

      <div>
        <div className="mb-2 flex items-center justify-between border-b border-tm-rule pb-1.5">
          <span className="font-tm-mono text-[10px] uppercase tracking-[0.08em] text-tm-muted">
            {t(locale, "sim.positions.title")}
          </span>
          <TwoStepConfirm
            idleLabel={t(locale, "sim.reset_btn")}
            warnText={t(locale, "sim.reset_confirm")}
            doneText={t(locale, "sim.reset_done")}
            onConfirm={handleReset}
          />
        </div>
        {account.positions.length === 0 ? (
          <div className="flex flex-col items-start gap-2 py-2">
            <p className="font-tm-mono text-[11px] text-tm-muted">{t(locale, "sim.overview.empty_hint")}</p>
            <TmButton variant="ghost" onClick={onGoToTrade}>
              {t(locale, "sim.overview.empty_cta")}
            </TmButton>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left">
              <thead>
                <tr className="border-b border-tm-rule">
                  {POS_HEADERS[locale].map((h) => (
                    <th
                      key={h}
                      className="px-3 py-1.5 font-tm-mono text-[10px] uppercase tracking-wide text-tm-muted text-right first:text-left"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {account.positions.map((p) => (
                  <SimPositionRow key={p.ticker} pos={p} locale={locale} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <Disclaimer />
    </div>
  );
}
