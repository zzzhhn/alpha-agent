"use client";

import { useEffect, useState } from "react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { useTimezonePreference } from "@/hooks/useTimezonePreference";
import { TmDrawer } from "@/components/tm/TmDrawer";
import { TmButton } from "@/components/tm/TmButton";
import { fetchPaperBotPositionReviews, type PaperBotPositionReview as Review } from "@/lib/api/paper-bot";
import { t } from "@/lib/i18n";
import { PaperBotState, botZonedTime } from "./PaperBotUi";

/** Only read existing model notes on demand; opening this drawer never wakes a bot. */
export default function PaperBotPositionReview({accountId,ticker,onClose,onRun}: {
  readonly accountId:number; readonly ticker:string; readonly onClose:()=>void; readonly onRun:(id:string)=>void;
}) {
  const {locale}=useLocale();
  const { timeZone } = useTimezonePreference();
  const [review,setReview]=useState<Review | null>(null);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState<unknown>(null);
  const [revision,setRevision]=useState(0);
  useEffect(()=>{
    let cancelled=false;
    setLoading(true);setError(null);setReview(null);
    void fetchPaperBotPositionReviews(accountId).then(data=>{
      if(!cancelled)setReview(data.positions.find(row=>row.ticker===ticker) ?? null);
    }).catch(reason=>{if(!cancelled)setError(reason);}).finally(()=>{if(!cancelled)setLoading(false);});
    return ()=>{cancelled=true;};
  },[accountId,ticker,revision]);
  return <TmDrawer open onClose={onClose} closeLabel={t(locale,"sim.bot.close")} title={`${ticker} · ${t(locale,"sim.bot.holding_review")}`} width="lg">
    {loading || error ? <PaperBotState loading={loading} error={error} onRetry={()=>setRevision(value=>value+1)} /> : review?.run_id ? <div className="space-y-5 text-sm leading-6">
      <p className="text-xs text-tm-muted">{t(locale,"sim.bot.review_scope")}</p>
      <p className="whitespace-pre-wrap break-words text-tm-fg">{review.note || "—"}</p>
      <dl className="space-y-4">{(["thesis","invalidation","review_after"] as const).map(key=><div key={key}><dt className="text-xs text-tm-muted">{t(locale,`sim.bot.position_${key}`)}</dt><dd className="mt-1 whitespace-pre-wrap break-words text-tm-fg">{review[key] || "—"}</dd></div>)}</dl>
      <p className="font-tm-mono text-xs text-tm-muted">{t(locale,"sim.bot.reviewed_at")} · {review.updated_at ? `${botZonedTime(review.updated_at,locale,timeZone)}` : "—"}</p>
      <TmButton variant="secondary" onClick={()=>onRun(review.run_id!)}>{t(locale,"sim.bot.source_run")}</TmButton>
    </div> : <p className="text-sm leading-6 text-tm-muted">{t(locale,"sim.bot.review_missing")}</p>}
  </TmDrawer>;
}
