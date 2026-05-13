import AlertTimeline from "@/components/alerts/AlertTimeline";
import { TmScreen, TmPane } from "@/components/tm/TmPane";
import { TmSubbar, TmSubbarKV, TmSubbarSep } from "@/components/tm/TmSubbar";

export const dynamic = "force-dynamic";

interface PageProps {
  searchParams?: { ticker?: string };
}

export default function AlertsPage({ searchParams }: PageProps) {
  const ticker = searchParams?.ticker?.toUpperCase();

  return (
    <TmScreen>
      <TmSubbar>
        <TmSubbarKV label="FEED" value="per-ticker timeline" />
        {ticker ? (
          <>
            <TmSubbarSep />
            <TmSubbarKV label="FILTER" value={ticker} />
          </>
        ) : null}
      </TmSubbar>

      <TmPane title="ALERTS" meta="alert_queue (M4b)">
        <AlertTimeline ticker={ticker} />
      </TmPane>
    </TmScreen>
  );
}
