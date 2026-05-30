// Per-grade chip styling for the /picks dimension ribbon (B8 grades:
// A+/A/B/C+/C/D/F plus "—" for missing). Tinted-block ramp: background is
// the hue at low opacity, text is the full-strength same hue, so contrast
// is guaranteed in both themes (tm-* tokens adapt) while the wash still
// reads as a green→gray→red heatmap. Matches the existing chip convention
// (bg-tm-accent/10 text-tm-accent) used by the subbar toggles.
//
// Grade thresholds (alpha_agent/fusion/grades.py grade_z):
//   A+ z>=1.5 · A z>=1.0 · B z>=0.5 · C+ z>=0.0 · C z>=-0.5 · D z>=-1.0 · F else

// Ramp tuned so the blocks are actually VISIBLE on the dark terminal bg —
// the first pass used /10–/25 opacities that washed out to near-invisible,
// degrading the "color block" choice into plain colored letters. Now the
// extremes (A+/F) are solid fills with inverted (tm-bg) text for max pop,
// and the mid grades are perceptible same-hue tint blocks with full-
// strength same-hue text (contrast guaranteed in both themes). Neutral C
// stays faintest so the heatmap's standouts catch the eye first.
const GRADE_CHIP: Record<string, string> = {
  "A+": "bg-tm-pos text-tm-bg font-semibold",
  A: "bg-tm-pos/40 text-tm-pos font-semibold",
  "A-": "bg-tm-pos/30 text-tm-pos",
  B: "bg-tm-pos/22 text-tm-pos",
  "C+": "bg-tm-fg-2/22 text-tm-fg-2",
  C: "bg-tm-fg-2/12 text-tm-muted",
  D: "bg-tm-neg/28 text-tm-neg",
  F: "bg-tm-neg text-tm-bg font-semibold",
};

const EMPTY_CHIP = "text-tm-muted/40";

/** className for a single grade chip. Unknown / "—" grades render faint. */
export function gradeChipClass(grade: string): string {
  return GRADE_CHIP[grade] ?? EMPTY_CHIP;
}

// Fixed dimension order + single-letter header. Keys MUST match
// DIMENSION_GROUPS in alpha_agent/fusion/grades.py exactly, or a dimension
// silently renders as a missing "—" cell.
export interface DimensionSpec {
  key: string;
  initial: string;
}

export const DIMENSION_ORDER: readonly DimensionSpec[] = [
  { key: "Momentum", initial: "M" },
  { key: "Technical", initial: "T" },
  { key: "Sentiment", initial: "S" },
  { key: "Catalyst", initial: "C" },
  { key: "Insider", initial: "I" },
  { key: "Flow", initial: "F" },
];
