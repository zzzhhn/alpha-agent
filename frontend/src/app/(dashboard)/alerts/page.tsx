import { fetchCronHealth } from "@/lib/api/alerts";
import AlertList from "@/components/alerts/AlertList";
import { TmScreen, TmPane } from "@/components/tm/TmPane";
import { TmSubbar, TmSubbarKV, TmSubbarSep } from "@/components/tm/TmSubbar";

export const dynamic = "force-dynamic";

export default async function AlertsPage() {
  const data = await fetchCronHealth();
  const jobCount = Object.keys(data.cron).length;
  const totalRuns = Object.values(data.cron).reduce((sum, runs) => sum + runs.length, 0);

  return (
    <TmScreen>
      <TmSubbar>
        <TmSubbarKV label="JOBS" value={String(jobCount)} />
        <TmSubbarSep />
        <TmSubbarKV label="TOTAL RUNS" value={String(totalRuns)} />
        <TmSubbarSep />
        <TmSubbarKV label="FEED" value="cron history · per-ticker in M4" />
      </TmSubbar>

      <TmPane
        title="CRON & ALERTS"
        meta="Phase 1: cron run history — real per-ticker alert feed deferred to M4"
      >
        <AlertList cronRuns={data.cron} />
      </TmPane>
    </TmScreen>
  );
}
