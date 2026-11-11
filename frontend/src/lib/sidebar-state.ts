/**
 * Desktop sidebar collapse preference. Stored in a cookie (not only
 * localStorage) so the server-rendered layout already has the right width and
 * the client hydrates without a visible jump.
 */
export const SIDEBAR_COOKIE = "alpha_sidebar";
export type SidebarMode = "expanded" | "collapsed";

export function parseSidebarMode(value: string | null | undefined): SidebarMode {
  return value === "collapsed" ? "collapsed" : "expanded";
}

export function persistSidebarMode(mode: SidebarMode): void {
  if (typeof document === "undefined") return;
  document.cookie = `${SIDEBAR_COOKIE}=${mode}; path=/; max-age=31536000; samesite=lax`;
}

export const SIDEBAR_WIDTH = { expanded: 200, collapsed: 56 } as const;
