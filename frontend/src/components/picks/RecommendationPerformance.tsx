"use client";

import { useState } from "react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { SegmentedTabs } from "@/components/ui/SegmentedTabs";
import InvestmentEvidence from "./InvestmentEvidence";

export default function RecommendationPerformance() {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const [sleeve, setSleeve] = useState<"tactical" | "strategic">("tactical");
  return <section aria-label={zh ? "推荐策略自动验证账户，与个人模拟仓独立" : "Automatic recommendation validation book, separate from your paper account"}>
    <SegmentedTabs active={sleeve} onChange={setSleeve} idBase="recommendation-nav"
      ariaLabel={zh ? "推荐验证策略" : "Recommendation validation policy"}
      items={[{ key: "tactical", label: zh ? "战术推荐净值" : "Tactical NAV" },
        { key: "strategic", label: zh ? "战略推荐净值" : "Strategic NAV" }]} />
    <div role="tabpanel" id={`recommendation-nav-panel-${sleeve}`} aria-labelledby={`recommendation-nav-tab-${sleeve}`}>
      <InvestmentEvidence key={sleeve} sleeve={sleeve} showStudy={false} />
    </div>
  </section>;
}
