"use client";

import { useState } from "react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { TmScreen } from "@/components/tm/TmPane";
import {
  TmSubbar,
  TmSubbarKV,
  TmSubbarSep,
  TmSubbarSpacer,
  TmStatusPill,
} from "@/components/tm/TmSubbar";
import { SegmentedTabs } from "@/components/ui/SegmentedTabs";
import { WorkbenchHeader } from "@/components/workbench/WorkbenchHeader";
import { t } from "@/lib/i18n";
import { ReferenceControls } from "./ReferenceControls";
import { ReferenceDataFeedback } from "./ReferenceDataFeedback";
import { ReferenceFoundations } from "./ReferenceFoundations";
import { ReferencePatterns } from "./ReferencePatterns";
import { ReferenceSurfaces } from "./ReferenceSurfaces";

type Section = "foundations" | "controls" | "data" | "feedback" | "surfaces" | "patterns";

export function DesignSystemReference() {
  const { locale } = useLocale();
  const [section, setSection] = useState<Section>("foundations");
  const zh = locale === "zh";
  const items = [
    { key: "foundations", label: t(locale, "reference.section.foundations") },
    { key: "controls", label: t(locale, "reference.section.controls") },
    { key: "data", label: t(locale, "reference.section.data") },
    { key: "feedback", label: t(locale, "reference.section.feedback") },
    { key: "surfaces", label: t(locale, "reference.section.surfaces") },
    { key: "patterns", label: t(locale, "reference.section.patterns") },
  ] satisfies ReadonlyArray<{ key: Section; label: string }>;

  return (
    <TmScreen>
      <WorkbenchHeader
        eyebrow={t(locale, "reference.eyebrow")}
        title={t(locale, "reference.title")}
        subtitle={t(locale, "reference.subtitle")}
        statuses={[
          {
            label: t(locale, "reference.status.coverage"),
            value: zh ? "首批已固化" : "Core batch fixed",
            tone: "positive",
          },
          {
            label: t(locale, "reference.status.version"),
            value: "2026.08",
          },
          {
            label: t(locale, "reference.status.theme"),
            value: zh ? "暗色 + 亮色" : "Dark + light",
          },
        ]}
      />

      <TmSubbar>
        <TmSubbarKV label="MODE" value={zh ? "生产组件" : "PRODUCTION ASSETS"} />
        <TmSubbarSep />
        <TmSubbarKV label="DENSITY" value="DESKTOP / COMPACT" />
        <TmSubbarSpacer />
        <TmStatusPill tone="warn">{t(locale, "reference.copy.sample")}</TmStatusPill>
      </TmSubbar>

      <SegmentedTabs
        idBase="reference-section"
        ariaLabel={zh ? "设计系统分类" : "Design system categories"}
        items={items}
        active={section}
        onChange={setSection}
      />

      <div
        id={`reference-section-panel-${section}`}
        role="tabpanel"
        aria-labelledby={`reference-section-tab-${section}`}
        className="min-h-0 flex-1"
      >
        {section === "foundations" ? <ReferenceFoundations locale={locale} /> : null}
        {section === "controls" ? <ReferenceControls locale={locale} /> : null}
        {section === "data" ? <ReferenceDataFeedback locale={locale} mode="data" /> : null}
        {section === "feedback" ? <ReferenceDataFeedback locale={locale} mode="feedback" /> : null}
        {section === "surfaces" ? <ReferenceSurfaces locale={locale} /> : null}
        {section === "patterns" ? <ReferencePatterns locale={locale} /> : null}
      </div>
    </TmScreen>
  );
}
