// frontend/src/lib/thesis.ts
import type { RatingCard, BreakdownEntry } from "./api/picks";
import { getSignalDisplayLabel } from "./signal-labels";
import type { Locale } from "./i18n";

export interface Thesis {
  bull: string[];
  bear: string[];
}

export function renderLeanThesis(
  card: RatingCard,
  locale: Locale = "en",
): Thesis {
  const lookup: Record<string, BreakdownEntry> = {};
  for (const b of card.breakdown) lookup[b.signal] = b;
  const zfmt = (z: number) => `z=${z >= 0 ? "+" : ""}${z.toFixed(2)}`;

  const bull = card.top_drivers.map((d) => {
    const z = lookup[d]?.z ?? 0;
    const label = getSignalDisplayLabel(d, locale);
    return locale === "zh"
      ? `${label} 信号正向贡献（${zfmt(z)}）`
      : `${label} signal contributing positively (${zfmt(z)})`;
  });
  const bear = card.top_drags.map((d) => {
    const z = lookup[d]?.z ?? 0;
    const label = getSignalDisplayLabel(d, locale);
    return locale === "zh"
      ? `${label} 信号负向拖累（${zfmt(z)}）`
      : `${label} signal pulling negatively (${zfmt(z)})`;
  });
  return {
    bull: bull.length
      ? bull
      : [locale === "zh" ? "未检测到明显的看多信号" : "No strongly positive signals detected"],
    bear: bear.length
      ? bear
      : [locale === "zh" ? "未检测到明显的看空信号" : "No strongly negative signals detected"],
  };
}
