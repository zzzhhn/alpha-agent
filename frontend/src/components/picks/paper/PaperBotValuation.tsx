"use client";

import { useLocale } from "@/components/layout/LocaleProvider";
import type { AccountResponse } from "@/lib/api/paper";
import { t } from "@/lib/i18n";
import { Metric } from "./PaperUi";
import { botTime } from "./PaperBotUi";

const money = (value: number) => `$${value.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
const tone = (value: number | null | undefined) => value ? value > 0 ? "text-tm-pos" : "text-tm-neg" : "text-tm-fg";

/** Display history without replacing current values consumed by trading APIs. */
export default function PaperBotValuation({ account }: { readonly account: AccountResponse | null }) {
  const { locale } = useLocale();
  const current = account?.portfolio_value != null && account.unrealized_pnl != null;
  const historical = !current ? account?.last_valid_valuation : null;
  const valuation = current ? account : historical;
  const pnl = valuation?.unrealized_pnl;
  const returns = valuation?.total_return_pct;
  return <>
    <div className="grid grid-cols-2 gap-4 px-6 py-4 sm:grid-cols-4">
      <Metric label={t(locale, historical ? "sim.bot.last_valid_nav" : "sim.account.nav")} value={valuation?.portfolio_value != null ? money(valuation.portfolio_value) : "—"} />
      <Metric label={t(locale,"sim.bot.current_cash")} value={account ? money(account.available_cash) : "—"} />
      <Metric label={t(locale,historical ? "sim.bot.snapshot_pnl" : "sim.account.unrealized")} value={pnl != null ? `${pnl > 0 ? "+" : pnl < 0 ? "-" : ""}${money(Math.abs(pnl))}` : "—"} tone={tone(pnl)} />
      <Metric label={t(locale,historical ? "sim.bot.snapshot_return" : "sim.workspace.total_return")} value={returns != null ? `${returns > 0 ? "+" : ""}${returns.toFixed(2)}%` : "—"} tone={tone(returns)} />
    </div>
    <div className="space-y-1 px-6 pb-3 text-xs leading-5">
      {valuation?.valued_at ? <p className={historical ? "text-tm-warn" : "text-tm-muted"}>
        {t(locale,historical ? "sim.bot.last_valid_at" : "sim.bot.valuation_snapshot")} · <time dateTime={valuation.valued_at}>{botTime(valuation.valued_at,locale)} CST</time>
        {historical ? ` · ${t(locale,"sim.bot.historical_not_live")}` : null}
      </p> : null}
      {!current && account && !historical ? <p role="status" className="text-tm-warn">{t(locale,"sim.bot.no_valid_valuation")}</p> : null}
      <p className="text-tm-muted">{t(locale,"sim.bot.valuation_cadence")}</p>
    </div>
  </>;
}
