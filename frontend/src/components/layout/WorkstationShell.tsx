"use client";

import { useCallback, useState, type ReactNode } from "react";
import { MobileNav, Sidebar } from "./Sidebar";
import { persistSidebarMode, SIDEBAR_WIDTH, type SidebarMode } from "@/lib/sidebar-state";

/**
 * Sidebar + content grid. Only the first grid track changes on collapse, so the
 * <main> subtree (page state, filters, pagination, scroll position) is never
 * remounted. The initial mode comes from the server-read cookie, so the first
 * paint already matches and hydration has nothing to correct.
 */
export function WorkstationShell({
  initialSidebar,
  children,
}: {
  readonly initialSidebar: SidebarMode;
  readonly children: ReactNode;
}) {
  const [mode, setMode] = useState<SidebarMode>(initialSidebar);
  const toggle = useCallback(() => {
    setMode((current) => {
      const next = current === "collapsed" ? "expanded" : "collapsed";
      persistSidebarMode(next);
      return next;
    });
  }, []);
  return (
    <>
      <MobileNav />
      <div
        className="grid min-h-0 flex-1 grid-cols-1 md:grid-cols-[var(--tm-sidebar-width)_minmax(0,1fr)]"
        style={{ "--tm-sidebar-width": `${SIDEBAR_WIDTH[mode]}px` } as React.CSSProperties}
        data-sidebar-mode={mode}
      >
        <Sidebar mode={mode} onToggle={toggle} />
        {/* No padding on <main>: pages render edge-to-edge as workstation
            screens (TmScreen establishes the bg-tm-bg floor itself). */}
        <main className="min-w-0 overflow-y-auto">{children}</main>
      </div>
    </>
  );
}
