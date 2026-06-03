// frontend/src/lib/suggestion.ts
import { t, type Locale } from "./i18n";

type I18nKey = Parameters<typeof t>[1];

export interface Suggestion {
  label: string;
  tone: "pos" | "neg" | "muted";
  // True when the calibrated directional hit-rate is at/below coin-flip, so an
  // actionable (buy/sell) call should be shown with a caution affordance. This
  // is the honesty gate from the "今日推荐 meaningful?" discussion: short-horizon
  // single-name edge is structurally modest, and the UI must say so rather than
  // dress a ~50% call up as conviction.
  caution: boolean;
}

const ACTION: Record<string, { key: I18nKey; tone: "pos" | "neg" | "muted" }> = {
  BUY: { key: "picks_table.sug_buy", tone: "pos" },
  OW: { key: "picks_table.sug_add", tone: "pos" },
  HOLD: { key: "picks_table.sug_hold", tone: "muted" },
  UW: { key: "picks_table.sug_trim", tone: "neg" },
  SELL: { key: "picks_table.sug_sell", tone: "neg" },
};

// Plain-language action for a rating tier, honesty-gated by the calibrated
// hit-rate (card.confidence). HOLD is never cautioned (it is already "wait").
export function getSuggestion(
  rating: string,
  hitRate: number,
  locale: Locale,
): Suggestion {
  const a = ACTION[rating] ?? ACTION.HOLD;
  const caution = a.tone !== "muted" && hitRate <= 0.5;
  return { label: t(locale, a.key), tone: a.tone, caution };
}
