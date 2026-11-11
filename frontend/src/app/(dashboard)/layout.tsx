/**
 * Dashboard layout — workstation chrome (Variation C, Stage 2).
 *
 * Server component (no hooks of its own) so it can read the locale cookie
 * via getServerLocale() and seed LocaleProvider with it — the client's first
 * render then matches SSR, eliminating the locale hydration mismatch
 * (React #425 / #422). The chrome (Topbar/Sidebar/etc.) are client components
 * rendered as children, which a server component renders fine.
 *
 * Composition:
 *   ┌──────────────────────────────────────────┐
 *   │ Topbar (titlebar: brand · status · toggles)│  ← auto height
 *   ├────────┬─────────────────────────────────┤
 *   │ Sidebar│  <main> (page content)          │  ← flex: 1, scrolls
 *   │200/56px│                                 │
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
import { cookies } from "next/headers";
import { Topbar } from "@/components/layout/Topbar";
import { WorkstationShell } from "@/components/layout/WorkstationShell";
import { SystemHealthProvider } from "@/components/layout/SystemHealth";
import { LocaleProvider } from "@/components/layout/LocaleProvider";
import VersionWatcher from "@/components/layout/VersionWatcher";
import { ToastProvider, ToastViewport } from "@/components/ui/toast";
import { getServerLocale } from "@/lib/server-locale";
import { parseSidebarMode, SIDEBAR_COOKIE } from "@/lib/sidebar-state";

interface DashboardLayoutProps {
  readonly children: ReactNode;
}

export default async function DashboardLayout({
  children,
}: DashboardLayoutProps) {
  const locale = await getServerLocale();
  const sidebar = parseSidebarMode((await cookies()).get(SIDEBAR_COOKIE)?.value);
  return (
    <ToastProvider>
      <LocaleProvider initialLocale={locale}>
        <SystemHealthProvider>
        <div className="flex h-screen flex-col bg-tm-bg text-tm-fg">
          <Topbar />
          <WorkstationShell initialSidebar={sidebar}>{children}</WorkstationShell>
        </div>
        <VersionWatcher />
        <ToastViewport />
        </SystemHealthProvider>
      </LocaleProvider>
    </ToastProvider>
  );
}
