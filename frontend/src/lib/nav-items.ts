import type { Locale } from "@/lib/i18n";

/**
 * Sidebar navigation registry. Each item carries both names so the active
 * locale leads and the other follows, without concatenating mixed i18n
 * strings. Routes are unchanged.
 */
export type NavItemId =
  | "picks" | "paper" | "alerts"
  | "alpha" | "backtest" | "screener" | "report"
  | "zoo" | "evolution" | "brain"
  | "guide" | "data" | "methodology" | "reference" | "settings";

export interface NavItem {
  readonly id: NavItemId;
  readonly href: string;
  readonly zh: string;
  readonly en: string;
}

export interface NavGroup {
  readonly id: "workflow" | "research" | "advanced" | "reference";
  readonly zh: string;
  readonly en: string;
  readonly secondary?: boolean;
  readonly items: readonly NavItem[];
}

export const NAV_GROUPS: readonly NavGroup[] = [
  {
    id: "workflow", zh: "每日工作流", en: "Daily workflow",
    items: [
      { id: "picks", href: "/picks", zh: "今日推荐", en: "Picks" },
      { id: "paper", href: "/paper", zh: "模拟仓", en: "Paper Trading" },
      { id: "alerts", href: "/alerts", zh: "警报", en: "Alerts" },
    ],
  },
  {
    id: "research", zh: "研究", en: "Research",
    items: [
      { id: "alpha", href: "/alpha", zh: "因子", en: "Alpha" },
      { id: "backtest", href: "/backtest", zh: "回测", en: "Backtest" },
      { id: "screener", href: "/screener", zh: "选股", en: "Screener" },
      { id: "report", href: "/report", zh: "报告", en: "Report" },
    ],
  },
  {
    id: "advanced", zh: "高级研究工具", en: "Advanced research", secondary: true,
    items: [
      { id: "zoo", href: "/factors", zh: "因子库", en: "Zoo" },
      { id: "evolution", href: "/evolution", zh: "演化监控", en: "Evolution" },
      { id: "brain", href: "/brain", zh: "BRAIN 挖矿", en: "BRAIN Mining" },
    ],
  },
  {
    id: "reference", zh: "参考", en: "Reference",
    items: [
      { id: "guide", href: "/guide", zh: "使用手册", en: "Guide" },
      { id: "data", href: "/data", zh: "数据", en: "Data" },
      { id: "methodology", href: "/methodology", zh: "方法论", en: "Methodology" },
      { id: "reference", href: "/reference", zh: "设计系统", en: "Design System" },
      { id: "settings", href: "/settings", zh: "设置", en: "Settings" },
    ],
  },
];

/** Active-locale name first, the other locale second. */
export function navLabels(item: Pick<NavItem, "zh" | "en">, locale: Locale) {
  return locale === "zh"
    ? { primary: item.zh, secondary: item.en }
    : { primary: item.en, secondary: item.zh };
}

/** Route sub-pages keep their parent active, e.g. /stock/X is not a nav item. */
export function isNavActive(pathname: string | null, href: string): boolean {
  if (!pathname) return false;
  return pathname === href || pathname.startsWith(`${href}/`);
}
