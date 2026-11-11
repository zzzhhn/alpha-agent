"use client";
import type { RatingCard, RecommendationRunState } from "@/lib/api/picks";
import { TmDrawer } from "@/components/tm/TmDrawer";
import InvestmentProfile from "./InvestmentProfile";
import InvestmentNotebook from "./InvestmentNotebook";
export default function ResearchRecords({ open, onClose, card, run, zh }: {
  open: boolean; onClose: () => void; card?: RatingCard; run?: RecommendationRunState | null; zh: boolean;
}) {
  const contextNotes = [card?.run_id ?? run?.run_id ? `${zh ? "快照" : "Run"} #${card?.run_id ?? run?.run_id}` : "",
    card?.market_date ?? run?.market_date, card?.policy_id ?? run?.policy_id].filter(Boolean).join(" · ");
  return <TmDrawer open={open} onClose={onClose} title={zh ? "研究记录" : "Research records"}
    description={zh ? "全局约束与逐股观点分别保存；不写记录也可浏览，不会启用机器人。" : "Constraints and ticker views are saved separately. Records are optional and never enable bots."}
    closeLabel={zh ? "关闭研究记录" : "Close research records"} width="xl">
    <div className="space-y-4">
      <InvestmentProfile compact />
      {open ? <InvestmentNotebook key={card?.ticker ?? "new"} ticker={card?.ticker} embedded contextNotes={contextNotes} /> : null}
    </div>
  </TmDrawer>;
}
