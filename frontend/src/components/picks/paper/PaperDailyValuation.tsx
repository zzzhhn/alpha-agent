import type { AccountResponse } from "@/lib/api/paper";

const money = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

export default function PaperDailyValuation({ account, locale }: {
  readonly account: AccountResponse;
  readonly locale: "zh" | "en";
}) {
  const zh = locale === "zh";
  const issues = account.valuation_issues ?? [];
  const reference = account.reference_valuation;
  if (account.valuation_quality === "orders_pending") {
    return <p role="status" className="px-6 pb-3 text-xs text-tm-muted">
      {zh ? "等待到期撮合完成后更新净值。" : "Equity updates after due orders finish processing."}
    </p>;
  }
  if (!issues.length) return null;

  return <div role="status" className="px-6 pb-3 text-xs leading-5 text-tm-muted">
    <p>{zh ? "本交易日收盘报价不齐，净值待核对。" : "Equity is pending complete closing quotes."}{" "}
      {issues.map(issue => issue.ticker).join(", ")}
    </p>
    {reference ? <p>
      {zh ? "参考估值" : "Indicative value"} {"$"}{money.format(reference.portfolio_value)}
      {" · "}{reference.valued_at.slice(0, 10)}{reference.valued_at.slice(0, 10) !== reference.market_date
        ? <> – {reference.market_date}</> : null}
    </p> : null}
  </div>;
}
