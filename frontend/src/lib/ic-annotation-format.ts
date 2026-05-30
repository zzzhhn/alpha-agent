// Templates an IC change annotation's STRUCTURED facts into a localized
// sentence (principle 11 traceability — the prose is built client-side from
// real facts, never an LLM cause). Kept pure so it can be unit-tested and
// reused by the chart tooltip + any future change-timeline.
import type { IcAnnotation, IcCoOccurringEvent } from "./api/evolution";
import { getSignalDisplayLabel } from "./signal-labels";
import { t, type Locale } from "./i18n";

function coOccurringLabel(ev: IcCoOccurringEvent, locale: Locale): string {
  if (ev.type === "weight_change") {
    const key =
      ev.source === "auto_rollback"
        ? "evolution.trace.ev_weight_rollback"
        : ev.source === "auto_promote"
          ? "evolution.trace.ev_weight_promote"
          : "evolution.trace.ev_weight_change";
    return t(locale, key as Parameters<typeof t>[1]);
  }
  return ev.type;
}

export interface FormattedIcAnnotation {
  // "因子 IC -0.21 → -0.05 (Δ+0.16)"
  headline: string;
  // "转负" / "crossed below zero" — only when sign_flip
  flipNote: string | null;
  // localized co-occurring event labels (may be empty)
  coOccurring: string[];
  // "无配置变更同期发生" / "no system change that day" when coOccurring empty
  noCause: string;
}

export function formatIcAnnotation(
  ann: IcAnnotation,
  locale: Locale,
): FormattedIcAnnotation {
  const label = getSignalDisplayLabel(ann.signal_name, locale);
  const prev = ann.prev ?? 0;
  const curr = ann.curr ?? 0;
  const delta = ann.delta ?? 0;
  const ds = delta >= 0 ? "+" : "";
  const headline = `${label} IC ${prev.toFixed(2)} → ${curr.toFixed(2)} (Δ${ds}${delta.toFixed(2)})`;

  let flipNote: string | null = null;
  if (ann.sign_flip) {
    flipNote = t(
      locale,
      curr < 0
        ? "evolution.trace.flip_negative"
        : "evolution.trace.flip_positive",
    );
  }

  const coOccurring = ann.co_occurring.map((ev) => coOccurringLabel(ev, locale));
  const noCause = t(locale, "evolution.trace.no_cause");

  return { headline, flipNote, coOccurring, noCause };
}
