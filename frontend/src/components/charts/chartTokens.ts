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

/** Ordered categorical series colors for multi-line and comparison charts. */
export const TM_CHART_SERIES_CSS = [
  "var(--tm-accent)",
  "var(--tm-info)",
  "var(--tm-pos)",
  "var(--tm-warn)",
  "var(--tm-neg)",
  "color-mix(in srgb, var(--tm-info) 62%, var(--tm-neg))",
  "color-mix(in srgb, var(--tm-info) 72%, var(--tm-pos))",
] as const;

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

/** Add alpha to a resolved hex or rgb token for canvas-based chart libraries. */
export function tmChartColorWithAlpha(color: string, alpha: number): string {
  const normalized = color.trim();
  const hex = normalized.match(/^#([\da-f]{2})([\da-f]{2})([\da-f]{2})$/i);
  if (hex) {
    return `rgba(${Number.parseInt(hex[1], 16)}, ${Number.parseInt(hex[2], 16)}, ${Number.parseInt(hex[3], 16)}, ${alpha})`;
  }
  const rgb = normalized.match(/^rgba?\((\d+)[,\s]+(\d+)[,\s]+(\d+)/i);
  if (rgb) return `rgba(${rgb[1]}, ${rgb[2]}, ${rgb[3]}, ${alpha})`;
  return normalized;
}
