import { TmScreen, TmPane } from "@/components/tm/TmPane";
import { TmSubbar, TmSubbarKV, TmSubbarSep } from "@/components/tm/TmSubbar";

// Route-level Suspense fallback. Without this file, Next.js shows a blank
// page during the RSC fetch in page.tsx — and because <Link> prefetch is
// effectively a no-op for force-dynamic routes, the user stares at the
// previous page for the full FastAPI roundtrip. The skeleton mirrors the
// real layout so the perceived shift on hydration is minimal.
export default function PicksLoading() {
  return (
    <TmScreen>
      <TmSubbar>
        <TmSubbarKV label="PICKS" value="—" />
        <TmSubbarSep />
        <TmSubbarKV label="AS OF" value="—" />
      </TmSubbar>
      <TmPane title="TODAY'S PICKS" meta="Loading...">
        <div className="flex items-center gap-2 px-3 py-2">
          <div className="h-7 w-56 animate-pulse rounded bg-tm-bg-2" />
        </div>
        <ul className="divide-y divide-tm-rule">
          {Array.from({ length: 12 }).map((_, i) => (
            <li
              key={i}
              className="flex items-center gap-3 px-3 py-2"
              style={{ opacity: 1 - i * 0.05 }}
            >
              <div className="h-4 w-12 animate-pulse rounded bg-tm-bg-2" />
              <div className="h-4 flex-1 animate-pulse rounded bg-tm-bg-2" />
              <div className="h-4 w-16 animate-pulse rounded bg-tm-bg-2" />
              <div className="h-4 w-10 animate-pulse rounded bg-tm-bg-2" />
            </li>
          ))}
        </ul>
      </TmPane>
    </TmScreen>
  );
}
