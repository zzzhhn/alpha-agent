import type { Locale } from "@/lib/i18n";
import type {
  AlertInboxItem,
  AlertRelevance,
  AlertSeverity,
} from "@/lib/api/alertsFeed";

export type AlertQueue = "needs_action" | "watch" | "record" | "resolved";

function facts(item: AlertInboxItem): Record<string, unknown> {
  return item.payload && !Array.isArray(item.payload) ? item.payload : {};
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function queueFor(item: AlertInboxItem): AlertQueue {
  if (item.state.status === "resolved") return "resolved";
  if (item.state.status === "snoozed") return "watch";
  if (item.triage_score >= 45) return "needs_action";
  if (item.triage_score >= 25) return "watch";
  return "record";
}

export function severityLabel(value: AlertSeverity, locale: Locale): string {
  const zh = locale === "zh";
  return {
    critical: zh ? "关键" : "Critical",
    warning: zh ? "警告" : "Warning",
    info: zh ? "信息" : "Info",
  }[value];
}

export function relevanceLabel(value: AlertRelevance, locale: Locale): string {
  const zh = locale === "zh";
  return {
    position: zh ? "当前持仓" : "Open position",
    recommendation: zh ? "今日候选" : "Today pick",
    market: zh ? "市场层面" : "Market-wide",
    watchlist: zh ? "关注列表" : "Watchlist",
    record: zh ? "仅记录" : "Record only",
  }[value];
}

export function alertTypeLabel(item: AlertInboxItem, locale: Locale): string {
  const zh = locale === "zh";
  return {
    rating_change: zh ? "评级变化" : "Rating change",
    score_spike: zh ? "评分跳变" : "Score spike",
    gap_3sigma: zh ? "盘前跳空" : "Premarket gap",
    iv_spike: zh ? "隐含波动率异常" : "IV spike",
    news_velocity: zh ? "新闻速度异常" : "News velocity",
  }[item.type] ?? item.type;
}

export function changeSummary(item: AlertInboxItem, locale: Locale): string {
  const zh = locale === "zh";
  const payload = facts(item);
  if (item.type === "rating_change") {
    const from = String(payload.from ?? "?");
    const to = String(payload.to ?? "?");
    return zh ? `评级从 ${from} 调整为 ${to}` : `Rating moved from ${from} to ${to}`;
  }
  if (item.type === "score_spike") {
    const delta = numberValue(payload.delta);
    return zh
      ? `综合评分出现${delta == null ? "显著" : ` ${delta >= 0 ? "+" : ""}${delta.toFixed(2)}`} 跳变`
      : `Composite score moved ${delta == null ? "materially" : `${delta >= 0 ? "+" : ""}${delta.toFixed(2)}`}`;
  }
  if (item.type === "gap_3sigma") {
    const sigma = numberValue(payload.gap_sigma);
    return zh
      ? `盘前价格偏离${sigma == null ? "超过阈值" : ` ${sigma.toFixed(1)}σ`}`
      : `Premarket move ${sigma == null ? "crossed threshold" : `${sigma.toFixed(1)}σ`}`;
  }
  if (item.type === "iv_spike") {
    const percentile = numberValue(payload.iv_percentile);
    return zh
      ? `隐含波动率升至${percentile == null ? "高分位" : `第 ${percentile.toFixed(0)} 百分位`}`
      : `Implied volatility reached ${percentile == null ? "a high percentile" : `p${percentile.toFixed(0)}`}`;
  }
  if (item.type === "news_velocity") {
    const count = numberValue(payload.n_24h);
    return zh
      ? `24 小时新闻数量${count == null ? "异常上升" : `增至 ${count.toFixed(0)} 条`}`
      : `24h news count ${count == null ? "accelerated" : `rose to ${count.toFixed(0)}`}`;
  }
  return zh ? "检测到结构化数据变化" : "A structured data change was detected";
}

export function impactSummary(item: AlertInboxItem, locale: Locale): string {
  const zh = locale === "zh";
  if (item.relevance === "position") {
    return zh ? "该标的在当前模拟仓中，需要复核原持仓依据。" : "This ticker is held in paper trading; review the original position thesis.";
  }
  if (item.relevance === "recommendation") {
    const rank = item.context.recommendation_rank;
    return zh
      ? `该标的属于最新推荐${rank ? `，当前排名 #${rank}` : ""}。`
      : `This ticker is in the latest recommendation${rank ? ` at rank #${rank}` : ""}.`;
  }
  if (item.relevance === "market") {
    return zh ? "这是市场层级变化，可能影响组合风险背景。" : "This is a market-level change that may alter portfolio risk context.";
  }
  if (item.relevance === "watchlist") {
    return zh ? "该标的位于关注列表，但未关联当前持仓或推荐。" : "This ticker is watched but not linked to a current position or recommendation.";
  }
  return zh ? "当前没有关联到持仓、推荐或关注列表。" : "No current position, recommendation, or watchlist link was found.";
}

export function relativeTime(iso: string, locale: Locale): string {
  const minutes = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 60000));
  if (minutes < 1) return locale === "zh" ? "刚刚" : "just now";
  if (minutes < 60) return locale === "zh" ? `${minutes} 分钟前` : `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return locale === "zh" ? `${hours} 小时前` : `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return locale === "zh" ? `${days} 天前` : `${days}d ago`;
}

export function evidenceRows(item: AlertInboxItem): Array<[string, string]> {
  const payload = facts(item);
  return Object.entries(payload)
    .filter(([, value]) => value != null && typeof value !== "object")
    .slice(0, 8)
    .map(([key, value]) => [key, String(value)]);
}
