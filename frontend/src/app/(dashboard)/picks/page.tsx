import { fetchPicks } from "@/lib/api/picks";
import PicksTable from "@/components/picks/PicksTable";
import { TmScreen, TmPane } from "@/components/tm/TmPane";
import { TmSubbar, TmSubbarKV, TmSubbarSep, TmStatusPill } from "@/components/tm/TmSubbar";

export const dynamic = "force-dynamic";

export default async function PicksPage() {
  const data = await fetchPicks(20);
  const asOf = data.as_of ? new Date(data.as_of).toLocaleString() : "—";

  return (
    <TmScreen>
      <TmSubbar>
        <TmSubbarKV label="PICKS" value={`${data.picks.length} signals`} />
        <TmSubbarSep />
        <TmSubbarKV label="AS OF" value={asOf} />
        {data.stale ? (
          <>
            <TmSubbarSep />
            <TmStatusPill tone="err">DATA &gt; 24h OLD</TmStatusPill>
          </>
        ) : null}
      </TmSubbar>

      <TmPane
        title="TODAY'S PICKS"
        meta={`sorted by composite score (desc) · top ${data.picks.length}`}
      >
        <PicksTable picks={data.picks} />
      </TmPane>
    </TmScreen>
  );
}
