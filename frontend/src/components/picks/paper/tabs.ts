// Shared tab constants for /paper. NO "use client" directive on purpose: the
// server component (app/(dashboard)/paper/page.tsx) imports PAPER_TABS to
// validate ?tab=, and a value imported ACROSS the client boundary arrives as a
// client-reference proxy whose methods throw at request time ("Attempted to
// call includes() from the server") — tsc and next build are both blind to it.
export type PaperTabKey = "overview" | "trade" | "curve" | "orders";
export const PAPER_TABS: readonly PaperTabKey[] = ["overview", "trade", "curve", "orders"];
