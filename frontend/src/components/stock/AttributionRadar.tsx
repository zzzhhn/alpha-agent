"use client";

import type { RatingCard } from "@/lib/api/picks";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { buildAttributionDimensions } from "@/lib/attribution-dimensions";
import { TmRadarChart } from "@/components/charts/TmRadarChart";

// Fixed radar scale [0, 3] sigma so visualization stays stable across tickers
// instead of auto-scaling to the largest z in the breakdown.
const RADAR_MAX = 3;

export default function AttributionRadar({ card }: { card: RatingCard }) {
  const { locale } = useLocale();
  const dimensions = buildAttributionDimensions(card);
  const data = dimensions.map((dimension) => {
    const z = dimension.score;
    return {
      label: t(locale, dimension.labelKey),
      positive: z !== null && z > 0 ? Math.min(z, RADAR_MAX) : 0,
      negative: z !== null && z < 0 ? Math.min(-z, RADAR_MAX) : 0,
      raw: z,
    };
  });
  const unavailable = dimensions.filter((dimension) => !dimension.available);
  const availableCount = dimensions.length - unavailable.length;
  const unavailableLabels = unavailable.map((dimension) => t(locale, dimension.labelKey));
  const coverageSummary = locale === "zh"
    ? `六维可比数据 ${availableCount}/6。与维度评级共用市场横截面标准化，不按个人权重调整。原始信号贡献见归因明细。`
    : `${availableCount}/6 comparable dimensions. Uses the grades' cross-sectional normalization, independent of personal weights. Signal contributions are in the attribution table.`;

  return (
    <>
      <TmRadarChart
        data={data}
        positiveLabel={t(locale, "radar.bullish")}
        negativeLabel={t(locale, "radar.bearish")}
        unavailableLabel={t(locale, "radar.unavailable")}
        maximum={RADAR_MAX}
        ariaLabel={locale === "zh" ? "六维股票信号归因雷达图" : "Six-dimension stock signal attribution radar chart"}
        summary={coverageSummary}
      />
      {unavailable.length > 0 ? (
        <p className="mt-1 text-center text-xs leading-5 text-tm-muted">
          {t(locale, "radar.unavailable_dimensions")}{locale === "zh" ? "：" : ": "}
          {unavailableLabels.join(locale === "zh" ? "、" : ", ")}
        </p>
      ) : null}
    </>
  );
}
