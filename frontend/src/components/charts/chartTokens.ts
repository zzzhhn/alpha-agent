export const TM_CHART_CSS = {
  positive: "var(--tm-pos)",
  negative: "var(--tm-neg)",
  warning: "var(--tm-warn)",
  information: "var(--tm-info)",
  foreground: "var(--tm-fg)",
  secondary: "var(--tm-fg-2)",
  muted: "var(--tm-muted)",
  grid: "var(--tm-rule)",
  gridStrong: "var(--tm-rule-2)",
  surface: "var(--tm-bg-2)",
} as const;

export type TmChartPalette = {
  readonly [Key in keyof typeof TM_CHART_CSS]: string;
};

/** Resolve chart colors for canvas libraries that cannot consume CSS vars. */
export function readTmChartPalette(
  node?: Element | null,
): TmChartPalette | null {
  if (typeof window === "undefined") return null;
  const target = node ?? document.documentElement;
  const styles = window.getComputedStyle(target);
  return Object.fromEntries(
    Object.entries(TM_CHART_CSS).map(([key, cssValue]) => {
      const token = cssValue.slice(4, -1);
      return [key, styles.getPropertyValue(token).trim()];
    }),
  ) as TmChartPalette;
}
