"use client";

/**
 * Data page — universe / sectors / schema / operator catalog / coverage.
 *
 * Stage 3 redesign re-port — uses TmScreen edge-to-edge stack with
 * tm-subbar at top + flat pane stack below. All data fetching, caching,
 * cancelled-effect cleanup unchanged.
 */

import { useCallback, useEffect, useState } from "react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { TmScreen, TmPane } from "@/components/tm/TmPane";
import {
  TmSubbar,
  TmSubbarKV,
  TmSubbarSep,
  TmSubbarSpacer,
  TmStatusPill,
  TmChip,
} from "@/components/tm/TmSubbar";
import { TmButton } from "@/components/tm/TmButton";
import { UniverseDetail } from "@/components/data/UniverseCard";
import { OperandCatalog } from "@/components/data/OperandCatalog";
import { CoverageOverview } from "@/components/data/CoverageOverview";
import {
  fetchUniverses,
  fetchOperandCatalog,
  fetchCoverage,
  invalidateDataCache,
} from "@/lib/api";
import type {
  UniverseListResponse,
  UniverseInfo,
  OperandCatalogResponse,
  CoverageResponse,
} from "@/lib/types";

export default function DataPage() {
  const { locale } = useLocale();
  const [universes, setUniverses] = useState<UniverseListResponse | null>(null);
  const [activeUniverseId, setActiveUniverseId] = useState<string | null>(null);
  const [catalog, setCatalog] = useState<OperandCatalogResponse | null>(null);
  const [coverage, setCoverage] = useState<CoverageResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async (force = false) => {
    const [u, o, c] = await Promise.all([
      fetchUniverses({ force }),
      fetchOperandCatalog({ force }),
      fetchCoverage("SP500_subset", { force }),
    ]);
    if (u.error || o.error || c.error) {
      setError(u.error ?? o.error ?? c.error);
      return;
    }
    setError(null);
    setUniverses(u.data);
    if (u.data && !activeUniverseId && u.data.universes.length > 0) {
      setActiveUniverseId(u.data.universes[0].id);
    }
    setCatalog(o.data);
    setCoverage(c.data);
  }, [activeUniverseId]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      await load(false);
      if (cancelled) return;
    })();
    return () => {
      cancelled = true;
    };
  }, [load]);

  async function handleRefresh() {
    setRefreshing(true);
    invalidateDataCache();
    await load(true);
    setRefreshing(false);
  }

  const activeUniverse: UniverseInfo | null =
    (universes &&
      activeUniverseId &&
      universes.universes.find((u) => u.id === activeUniverseId)) ||
    universes?.universes[0] ||
    null;

  return (
    <TmScreen>
      <TmSubbar>
        <span className="text-tm-muted">UNIVERSE</span>
        {universes
          ? universes.universes.map((u) => (
              <TmChip
                key={u.id}
                on={u.id === activeUniverse?.id}
                onClick={() => setActiveUniverseId(u.id)}
              >
                {u.id}
              </TmChip>
            ))
          : (
              <span className="text-tm-muted">{t(locale, "data.loading")}</span>
            )}
        {activeUniverse && (
          <>
            <TmSubbarSep />
            <TmSubbarKV
              label={t(locale, "data.universe.benchmark")}
              value={activeUniverse.benchmark}
            />
            <TmSubbarSep />
            <TmSubbarKV
              label="N"
              value={activeUniverse.ticker_count.toString()}
            />
          </>
        )}
        <TmSubbarSpacer />
        {coverage && (
          <TmStatusPill
            tone={coverage.ohlcv_coverage_pct >= 99 ? "ok" : "warn"}
          >
            CACHE · {coverage.ohlcv_coverage_pct.toFixed(2)}% HIT
          </TmStatusPill>
        )}
        <TmButton
          variant="ghost"
          onClick={handleRefresh}
          disabled={refreshing || !universes}
          className="-my-1 px-2"
        >
          {refreshing ? t(locale, "data.refreshing") : t(locale, "data.refresh")}
        </TmButton>
      </TmSubbar>

      {error && (
        <TmPane title="ERROR" meta={t(locale, "data.error")}>
          <p className="px-3 py-2.5 font-tm-mono text-[11px] text-tm-neg">
            {error}
          </p>
        </TmPane>
      )}

      {!error && !universes && (
        <TmPane title="LOADING">
          <p className="px-3 py-2.5 font-tm-mono text-[11px] text-tm-muted">
            {t(locale, "data.loading")}
          </p>
        </TmPane>
      )}

      {/* Active universe detail — title shows the universe id */}
      {activeUniverse && <UniverseDetail universe={activeUniverse} />}

      {catalog && <OperandCatalog catalog={catalog} />}

      {coverage && <CoverageOverview coverage={coverage} />}
    </TmScreen>
  );
}
