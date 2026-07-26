import PaperScreen, { PAPER_TABS, type PaperTabKey } from "@/components/picks/paper/PaperScreen";

// /paper — the standalone 模拟仓 route (V2 redesign). Server component so the
// initial tab is resolved from the URL query without needing a client-side
// useSearchParams() + <Suspense> boundary (mirrors the /alerts page pattern:
// searchParams as a page prop). PaperScreen (client) owns all further tab
// switches via router.replace.
export const dynamic = "force-dynamic";

interface PageProps {
  readonly searchParams?: { tab?: string };
}

function normalizeTab(raw: string | undefined): PaperTabKey {
  return (PAPER_TABS as readonly string[]).includes(raw ?? "")
    ? (raw as PaperTabKey)
    : "overview";
}

export default function PaperPage({ searchParams }: PageProps) {
  const tab = normalizeTab(searchParams?.tab);
  return <PaperScreen initialTab={tab} />;
}
