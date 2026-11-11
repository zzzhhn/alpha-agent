import type { Locale } from "@/lib/i18n";
import type { NavItemId } from "@/lib/nav-items";

/** Mirrors alpha_agent/api/nav_status.py. Unknown values degrade to "unknown". */
export type PicksNavState = "current" | "awaiting_publish" | "delayed" | "stale" | "failed" | "unknown";
export type EvolutionNavState =
  | "running" | "idle" | "awaiting_schedule" | "schedule_missed" | "failed"
  | "paused_after_failure" | "disabled" | "not_configured" | "unknown";

export interface NavStatusResponse {
  readonly as_of: string;
  readonly picks: {
    readonly state: PicksNavState;
    readonly reason: string | null;
    readonly market_date: string | null;
    readonly expected_market_date: string;
    readonly sessions_behind: number;
    readonly next_publish_at: string | null;
  };
  readonly evolution: {
    readonly state: EvolutionNavState;
    readonly workflow_state: string | null;
    readonly last_run_at: string | null;
    readonly last_run_ok: boolean | null;
    readonly pending_reviews: number | null;
  };
}

export interface AlertAttention {
  readonly needs_action: number;
  readonly critical: number;
  readonly window: number;
  readonly newest_at: string | null;
  readonly as_of: string;
  readonly source_status: "fresh" | "stale" | "empty";
}

/** Tone drives color; the marker and text carry the meaning on their own. */
export type NavSignalTone = "attention" | "warning" | "negative" | "muted" | "info";

export interface NavSignal {
  readonly tone: NavSignalTone;
  /** Short visible text (badge). Kept to a few characters. */
  readonly badge: string;
  /** Tooltip / accessible description with the evidence and next step. */
  readonly detail: string;
  /** In-page anchor the item focuses on click, when one exists. */
  readonly hash?: string;
}

export const ALERT_BADGE_CAP = 99;

const fmtDate = (value: string | null | undefined) => value ?? "—";

function fmtInstant(value: string | null | undefined): string {
  if (!value) return "—";
  const instant = new Date(value);
  if (!Number.isFinite(instant.getTime())) return "—";
  // UTC keeps SSR and client text identical; the label says so explicitly.
  const iso = instant.toISOString();
  return `${iso.slice(5, 10)} ${iso.slice(11, 16)} UTC`;
}

export function picksSignal(status: NavStatusResponse["picks"] | null, failed: boolean, locale: Locale): NavSignal | null {
  const zh = locale === "zh";
  if (failed || !status) {
    return {
      tone: "muted", badge: "?",
      detail: zh ? "推荐状态暂时无法读取，不代表正常或故障。" : "Recommendation status could not be read; this is not proof of either health or failure.",
    };
  }
  const latest = fmtDate(status.market_date);
  const expected = fmtDate(status.expected_market_date);
  const next = fmtInstant(status.next_publish_at);
  switch (status.state) {
    case "current":
      return null;
    case "awaiting_publish":
      return {
        tone: "info", badge: zh ? "待发布" : "Due",
        detail: zh
          ? `交易日 ${expected} 已收盘，快照仍在正常发布窗口内（约 ${next} 开始）。当前显示 ${latest}。`
          : `Session ${expected} closed; its snapshot is still within the normal publication window (from about ${next}). Showing ${latest}.`,
      };
    case "delayed":
      return {
        tone: "warning", badge: zh ? "延迟" : "Late",
        detail: zh
          ? `交易日 ${expected} 的快照尚未发布，页面仍是 ${latest}，不可交易。下一次自然发布约 ${next}。`
          : `The ${expected} snapshot has not been published; the page still shows ${latest} and is not tradable. Next natural publication about ${next}.`,
      };
    case "stale":
      return {
        tone: "warning", badge: zh ? `落后${status.sessions_behind}日` : `${status.sessions_behind}d behind`,
        detail: zh
          ? `最新快照 ${latest}，落后最近完成交易日 ${expected} 共 ${status.sessions_behind} 个交易日。`
          : `Latest snapshot ${latest} is ${status.sessions_behind} sessions behind ${expected}.`,
      };
    case "failed":
      return {
        tone: "negative", badge: zh ? "失败" : "Failed",
        detail: zh
          ? `交易日 ${expected} 的发布尝试失败（${status.reason ?? "未记录原因"}），仍显示 ${latest}。`
          : `Publishing ${expected} failed (${status.reason ?? "reason not recorded"}); still showing ${latest}.`,
      };
    default:
      return {
        tone: "muted", badge: "?",
        detail: zh ? "尚无已发布的推荐快照。" : "No recommendation snapshot has been published.",
      };
  }
}

export function alertsSignal(
  attention: AlertAttention | null,
  state: "signed_out" | "error" | "ok" | "loading",
  locale: Locale,
): NavSignal | null {
  const zh = locale === "zh";
  if (state === "signed_out" || state === "loading") return null;
  if (state === "error" || !attention) {
    return {
      tone: "muted", badge: "?",
      detail: zh ? "待处理警报数暂时无法读取。" : "Pending alert count could not be read.",
    };
  }
  const n = attention.needs_action;
  const scope = zh ? `最近 ${attention.window} 条内` : `within the latest ${attention.window}`;
  if (n === 0) {
    return attention.source_status === "stale"
      ? {
          tone: "muted", badge: zh ? "源旧" : "Old",
          detail: zh ? "没有待处理警报，但警报来源超过 24 小时未更新。" : "Nothing to review, but the alert source has not updated for over 24 hours.",
        }
      : null;
  }
  const shown = n > ALERT_BADGE_CAP ? `${ALERT_BADGE_CAP}+` : String(n);
  return {
    tone: attention.critical > 0 ? "negative" : "attention",
    badge: shown,
    detail: zh
      ? `${scope}有 ${n} 条需处理${attention.critical ? `，其中 ${attention.critical} 条高严重度` : ""}。已处理和暂缓的不计入。`
      : `${n} to review ${scope}${attention.critical ? `, ${attention.critical} critical` : ""}. Resolved and snoozed alerts are excluded.`,
  };
}

export function evolutionSignal(status: NavStatusResponse["evolution"] | null, failed: boolean, locale: Locale): NavSignal | null {
  const zh = locale === "zh";
  if (failed || !status) {
    return {
      tone: "muted", badge: "?",
      detail: zh ? "演化任务状态暂时无法读取。" : "Evolution task status could not be read.",
    };
  }
  const last = fmtInstant(status.last_run_at);
  const pending = status.pending_reviews ?? 0;
  const review: NavSignal | null = pending > 0
    ? {
        tone: "attention", badge: pending > ALERT_BADGE_CAP ? `${ALERT_BADGE_CAP}+` : String(pending),
        detail: zh ? `${pending} 项提案待审查。` : `${pending} proposals await review.`,
        hash: "evolution-review",
      }
    : null;
  const withPending = (text: string) => (pending > 0 ? `${text} ${zh ? `另有 ${pending} 项提案待审查。` : `${pending} proposals await review.`}` : text);
  switch (status.state) {
    case "idle":
    case "running":
    case "awaiting_schedule":
      return review;
    case "disabled":
      return {
        tone: "muted", badge: zh ? "已暂停" : "Paused",
        detail: withPending(zh ? `每日因子循环已被主动停用，不是故障。上次运行 ${last}。` : `The daily factor loop is deliberately disabled, not failing. Last run ${last}.`),
        hash: review?.hash,
      };
    case "paused_after_failure":
      return {
        tone: "warning", badge: zh ? "失败后暂停" : "Paused",
        detail: withPending(zh ? `上次运行 ${last} 失败后，每日因子循环已暂停，需要人工复核后再启用。` : `The daily factor loop was paused after its ${last} run failed; review before re-enabling.`),
        hash: review?.hash,
      };
    case "failed":
      return {
        tone: "negative", badge: zh ? "失败" : "Failed",
        detail: withPending(zh ? `上次运行 ${last} 失败。` : `The last run at ${last} failed.`),
      };
    case "schedule_missed":
      return {
        tone: "warning", badge: zh ? "未到达" : "Missed",
        detail: withPending(zh ? `计划运行未按时到达，上次运行 ${last}。` : `A scheduled run did not arrive; last run ${last}.`),
      };
    case "not_configured":
      return {
        tone: "muted", badge: zh ? "未配置" : "Not set",
        detail: zh ? "每日因子循环未配置。" : "The daily factor loop is not configured.",
      };
    default:
      return review ?? {
        tone: "muted", badge: "?",
        detail: zh ? "调度状态无法确认，不代表故障。" : "Scheduler state is unconfirmed; this is not proof of failure.",
      };
  }
}

export type NavSignals = Partial<Record<NavItemId, NavSignal>>;
