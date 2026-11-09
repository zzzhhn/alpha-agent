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
  const reference = !current ? account?.reference_valuation : null;
  const historical = !current && !reference ? account?.last_valid_valuation : null;
  const valuation = current ? account : reference ?? historical;
  const pnl = valuation?.unrealized_pnl;
  const returns = valuation?.total_return_pct;
  return <>
    <div className="grid grid-cols-2 gap-4 px-6 py-4 sm:grid-cols-4">
      <Metric label={t(locale, reference ? "sim.bot.reference_nav" : historical ? "sim.bot.last_valid_nav" : "sim.account.nav")} value={valuation?.portfolio_value != null ? money(valuation.portfolio_value) : "—"} />
      <Metric label={t(locale,"sim.bot.current_cash")} value={account ? money(account.available_cash) : "—"} />
      <Metric label={t(locale,reference ? "sim.bot.reference_pnl" : historical ? "sim.bot.snapshot_pnl" : "sim.account.unrealized")} value={pnl != null ? `${pnl > 0 ? "+" : pnl < 0 ? "-" : ""}${money(Math.abs(pnl))}` : "—"} tone={tone(pnl)} />
      <Metric label={t(locale,reference ? "sim.bot.reference_return" : historical ? "sim.bot.snapshot_return" : "sim.workspace.total_return")} value={returns != null ? `${returns > 0 ? "+" : ""}${returns.toFixed(2)}%` : "—"} tone={tone(returns)} />
    </div>
    <div className="space-y-1 px-6 pb-3 text-xs leading-5">
      {valuation?.valued_at ? <p className={historical || reference ? "text-tm-warn" : "text-tm-muted"}>
        {t(locale,reference ? "sim.bot.reference_range" : historical ? "sim.bot.last_valid_at" : "sim.bot.valuation_snapshot")} · <time dateTime={valuation.valued_at}>{botTime(valuation.valued_at,locale)} CST</time>
        {reference && reference.newest_mark_at !== reference.valued_at ? <> → <time dateTime={reference.newest_mark_at}>{botTime(reference.newest_mark_at,locale)} CST</time></> : null}
        {historical ? ` · ${t(locale,"sim.bot.historical_not_live")}` : null}
        {reference ? ` · ${t(locale,"sim.bot.reference_only")}` : null}
      </p> : null}
      {!valuation && account ? <p role="status" className="text-tm-warn">{t(locale,"sim.bot.no_valid_valuation")}</p> : null}
      {account?.valuation_issues?.length ? <details className="text-tm-muted"><summary className="cursor-pointer">{t(locale,"sim.bot.valuation_issues").replace("{n}",String(account.valuation_issues.length))}</summary><ul className="mt-1 max-h-40 overflow-y-auto">{account.valuation_issues.map(issue=><li key={issue.ticker} className="flex flex-wrap gap-x-2"><span className="font-tm-mono text-tm-fg">{issue.ticker}</span><span>{t(locale,issue.quality === "stale" ? "sim.bot.mark.stale" : issue.quality === "corporate_action_blocked" ? "sim.bot.mark.action" : "sim.bot.mark.missing")}</span>{issue.as_of ? <time dateTime={issue.as_of}>{botTime(issue.as_of,locale)} CST</time> : null}</li>)}</ul></details> : null}
      <p className="text-tm-muted">{t(locale,"sim.bot.valuation_cadence")}</p>
    </div>
  </>;
}
