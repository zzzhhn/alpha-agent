"use client";

/**
 * Data page — universe / operator catalog / coverage overview.
 *
 * Stage 3 redesign port. The 3 child components (UniverseCard,
 * OperandCatalog, CoverageOverview) each own their own TmPane, so this
 * page is a thin orchestrator: header pane + universe grid + catalog
 * + coverage. All data fetching, caching, error handling preserved
 * from the legacy implementation.
 *
 * NOT changed:
 *   * fetchUniverses / fetchOperandCatalog / fetchCoverage call sites
 *   * load() callback semantics (force=true on Refresh, force=false on mount)
 *   * invalidateDataCache() on refresh
 *   * cancelled-effect cleanup pattern
 *   * All i18n keys
 */

import { useCallback, useEffect, useState } from "react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { TmPane } from "@/components/tm/TmPane";
import { TmButton } from "@/components/tm/TmButton";
import { UniverseCard } from "@/components/data/UniverseCard";
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
  OperandCatalogResponse,
  CoverageResponse,
} from "@/lib/types";

export default function DataPage() {
  const { locale } = useLocale();
  const [universes, setUniverses] = useState<UniverseListResponse | null>(null);
  const [catalog, setCatalog] = useState<OperandCatalogResponse | null>(null);
  const [coverage, setCoverage] = useState<CoverageResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  // Caching design: fetchUniverses/Catalog/Coverage in lib/api.ts memoise
  // their promises at module scope. The first DataPage mount triggers the
  // network round-trips; subsequent mounts (e.g. after navigating to /alpha
  // and back) return the cached results synchronously. Full reload or an
  // explicit "刷新" click wipes the cache and re-fetches.
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
    setCatalog(o.data);
    setCoverage(c.data);
  }, []);

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

  return (
    <div className="flex flex-col gap-4 font-tm-mono">
      {/* Page header pane — title bar with subtitle in body, refresh CTA
          on the right. Mirrors the design's master-pane treatment. */}
      <TmPane
        title={t(locale, "data.title")}
        meta={
          universes ? (
            <TmButton
              variant="ghost"
              onClick={handleRefresh}
              disabled={refreshing}
              className="-my-1 px-2"
            >
              {refreshing
                ? t(locale, "data.refreshing")
                : t(locale, "data.refresh")}
            </TmButton>
          ) : null
        }
      >
        <p className="px-3 py-2.5 text-[11.5px] leading-relaxed text-tm-fg-2">
          {t(locale, "data.subtitle")}
        </p>
      </TmPane>

      {error && (
        <TmPane title="ERROR" meta={t(locale, "data.error")}>
          <p className="px-3 py-2.5 text-[11.5px] text-tm-neg">{error}</p>
        </TmPane>
      )}

      {!error && !universes && (
        <TmPane title="LOADING" meta="…">
          <p className="px-3 py-2.5 text-[11.5px] text-tm-muted">
            {t(locale, "data.loading")}
          </p>
        </TmPane>
      )}

      {universes && (
        <section className="flex flex-col gap-3">
          <h2 className="px-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-tm-muted">
            {t(locale, "data.universe.title")}
          </h2>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {universes.universes.map((u) => (
              <UniverseCard key={u.id} universe={u} />
            ))}
          </div>
        </section>
      )}

      {catalog && <OperandCatalog catalog={catalog} />}
      {coverage && <CoverageOverview coverage={coverage} />}
    </div>
  );
}
