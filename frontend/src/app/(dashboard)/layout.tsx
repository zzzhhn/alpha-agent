"use client";

/**
 * Dashboard layout — workstation chrome (Variation C, Stage 2).
 *
 * Composition:
 *   ┌──────────────────────────────────────────┐
 *   │ Topbar (titlebar: brand · status · toggles)│  ← auto height
 *   ├────────┬─────────────────────────────────┤
 *   │ Sidebar│  <main> (page content)          │  ← flex: 1, scrolls
 *   │ 200px  │                                 │
 *   └────────┴─────────────────────────────────┘
 *
 * Replaces the previous 260px Sidebar + 48px Topbar grid. Page bodies
 * still use their pre-redesign visual style — Stage 3 ports them onto
 * the new --tm-* tokens one at a time, starting with /settings.
 *
 * Note: the legacy Breadcrumb + ThemeToggle components still exist on
 * disk but are no longer imported by any layout. They will be removed
 * in Stage 5 once a final grep confirms no other consumers.
 */

import { type ReactNode } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { Topbar } from "@/components/layout/Topbar";
import { LocaleProvider } from "@/components/layout/LocaleProvider";

interface DashboardLayoutProps {
  readonly children: ReactNode;
}

export default function DashboardLayout({
  children,
}: DashboardLayoutProps) {
  return (
    <LocaleProvider>
      <div className="flex h-screen flex-col bg-tm-bg text-tm-fg">
        <Topbar />
        <div className="grid min-h-0 flex-1 grid-cols-[200px_1fr]">
          <Sidebar />
          {/* No padding on <main> — pages render edge-to-edge as
              workstation screens (TmScreen establishes the bg-tm-bg
              "floor" itself). Pages still using the legacy layout can
              add their own px/py inside their root. */}
          <main className="min-w-0 overflow-y-auto">{children}</main>
        </div>
      </div>
    </LocaleProvider>
  );
}
