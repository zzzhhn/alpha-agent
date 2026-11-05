"use client";

import { useState } from "react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { TmScreen, TmCols2, TmPane } from "@/components/tm/TmPane";
import { TmChip, TmSubbar, TmSubbarSpacer } from "@/components/tm/TmSubbar";
import { TmButton } from "@/components/tm/TmButton";
import { TmStatePane } from "@/components/tm/TmStatePane";
import { WorkbenchHeader } from "@/components/workbench/WorkbenchHeader";
import { UniverseOverview, UniverseCoverage, UniverseTickers } from "@/components/data/UniverseCard";
import { OperandCatalog } from "@/components/data/OperandCatalog";
import { DataSourcesCard } from "@/components/data/DataSourcesCard";
import { DataRequestState, useDataRequest } from "@/components/data/DataControls";
import { fetchUniverses, fetchOperandCatalog, fetchCoverage, invalidateDataCache } from "@/lib/api";

const loadUniverses = (_key: string, force: boolean) => fetchUniverses({ force });
const loadCatalog = (_key: string, force: boolean) => fetchOperandCatalog({ force });
async function loadCoverage(id: string, force: boolean) {
  const result = await fetchCoverage(id, { force });
  return result.data && result.data.universe_id !== id
    ? { data: null, error: "Coverage universe does not match selection." }
    : result;
}

export default function DataPage() {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [version, setVersion] = useState(0);
  const universes = useDataRequest("universes", version, loadUniverses);
  const catalog = useDataRequest("catalog", version, loadCatalog);
  const roster = universes.data?.universes ?? [];
  const active = roster.find((universe) => universe.id === selectedId) ?? roster[0];
  const coverage = useDataRequest(active?.id ?? null, version, loadCoverage);
  const refreshing = version > 0 && (universes.pending || catalog.pending || coverage.pending);
  const closePct = coverage.data && coverage.data.ohlcv_total_cells > 0
    ? coverage.data.ohlcv_coverage_pct
    : null;
  const catalogTitle = zh ? "因子表达式目录" : "Expression catalog";

  function refresh() {
    invalidateDataCache();
    setVersion((previous) => previous + 1);
  }

  return (
    <TmScreen className="shrink-0">
      <WorkbenchHeader
        title={zh ? "数据" : "Data"}
        subtitle={zh ? "核验股票池、字段覆盖与数据来源。" : "Verify universe, field coverage, and provenance."}
        statuses={active ? [{
          label: zh ? "样本截止" : "Sample through",
          value: active.end_date || "—",
        }] : undefined}
      />
      <TmSubbar>
        <span className="text-tm-muted">{zh ? "股票池" : "Universe"}</span>
        {roster.length > 1 ? roster.map((universe) => (
          <TmChip key={universe.id} on={universe.id === active?.id} onClick={() => setSelectedId(universe.id)}>
            {universe.id}
          </TmChip>
        )) : <span className="break-all font-semibold text-tm-fg">{active?.id ?? "—"}</span>}
        <TmSubbarSpacer />
        <TmButton variant="secondary" size="xs" onClick={refresh} disabled={universes.pending || catalog.pending || coverage.pending}>
          {t(locale, refreshing ? "data.refreshing" : "data.refresh")}
        </TmButton>
      </TmSubbar>

      <DataRequestState locale={locale} label={zh ? "股票池" : "universes"} request={universes} />
      {active ? (
        <TmCols2 className="lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
          <UniverseOverview key={`overview:${active.id}`} universe={active} closePct={closePct}>
            <DataRequestState locale={locale} label={zh ? "覆盖率" : "coverage"} request={coverage} />
          </UniverseOverview>
          <UniverseTickers key={`tickers:${active.id}`} universe={active} />
        </TmCols2>
      ) : universes.data ? (
        <TmStatePane state="empty" className="!min-h-24 border-x-0 !py-4" title={zh ? "未返回可用股票池" : "No universes returned"} />
      ) : null}

      {coverage.data && <UniverseCoverage key={coverage.data.universe_id} coverage={coverage.data} />}

      <DataSourcesCard version={version} />

      <TmPane title={catalogTitle}>
        <DataRequestState locale={locale} label={zh ? "目录" : "catalog"} request={catalog} />
        {catalog.data && <OperandCatalog catalog={catalog.data} />}
      </TmPane>
    </TmScreen>
  );
}
