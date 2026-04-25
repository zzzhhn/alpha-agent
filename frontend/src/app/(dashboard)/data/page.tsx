"use client";

import { useCallback, useEffect, useState } from "react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { UniverseCard } from "@/components/data/UniverseCard";
import { OperandCatalog } from "@/components/data/OperandCatalog";
import { CoverageHeatmap } from "@/components/data/CoverageHeatmap";
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
    <div className="flex flex-col gap-4 p-6">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-text">
            {t(locale, "data.title")}
          </h1>
          <p className="mt-1 max-w-3xl text-[12px] leading-relaxed text-muted">
            {t(locale, "data.subtitle")}
          </p>
        </div>
        {universes && (
          <Button
            variant="ghost"
            size="sm"
            onClick={handleRefresh}
            disabled={refreshing}
          >
            {refreshing ? t(locale, "data.refreshing") : t(locale, "data.refresh")}
          </Button>
        )}
      </header>

      {error && (
        <Card padding="md">
          <p className="text-sm text-red">
            {t(locale, "data.error")}: {error}
          </p>
        </Card>
      )}

      {!error && !universes && (
        <Card padding="md">
          <p className="text-sm text-muted">{t(locale, "data.loading")}</p>
        </Card>
      )}

      {universes && (
        <section className="flex flex-col gap-3">
          <h2 className="text-sm font-semibold text-text">
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
      {coverage && <CoverageHeatmap coverage={coverage} />}
    </div>
  );
}
