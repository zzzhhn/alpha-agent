// Per-grade chip styling for the /picks dimension ribbon (B8 grades:
// A+/A/B/C+/C/D/F plus "—" for missing). Tinted-block ramp: background is
// the hue at low opacity, text is the full-strength same hue, so contrast
// is guaranteed in both themes (tm-* tokens adapt) while the wash still
// reads as a green→gray→red heatmap. Matches the existing chip convention
// (bg-tm-accent/10 text-tm-accent) used by the subbar toggles.
//
// Grade thresholds (alpha_agent/fusion/grades.py grade_z):
//   A+ z>=1.5 · A z>=1.0 · B z>=0.5 · C+ z>=0.0 · C z>=-0.5 · D z>=-1.0 · F else

// Deviation-emphasis ramp (P0, after the §10 re-audit). The earlier
// "every cell is a visible block" version painted the neutral C+ majority
// as a sea of gray blocks that added cognitive load without information
// (violating rules 2 + 6). Now NEUTRAL recedes to faint text with no
// block, and only the standouts carry ink: strengthening grades (A/B) get
// green blocks, weakening grades (D/F) get red blocks. Scanning a column
// the eye lands only on what deviates from the neutral field — the
// heatmap "disappears" except where there's signal.
const GRADE_CHIP: Record<string, string> = {
  "A+": "bg-tm-pos text-tm-bg font-semibold",
  A: "bg-tm-pos-soft text-tm-pos font-semibold",
  "A-": "bg-tm-pos-soft text-tm-pos",
  B: "bg-tm-pos-soft text-tm-pos",
  // Neutral majority recedes: no background, faint text. Quiet field.
  "C+": "text-tm-fg-2",
  C: "text-tm-muted",
  // Weakness draws attention back — red blocks against the quiet field.
  D: "bg-tm-neg-soft text-tm-neg",
  F: "bg-tm-neg text-tm-bg font-semibold",
};

const EMPTY_CHIP = "text-tm-muted";

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
