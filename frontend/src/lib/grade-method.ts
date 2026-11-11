import type { GradeMethod } from "@/lib/api/picks";

export function gradeBand(grade: string, method?: GradeMethod): string {
  if (!method) return "—";
  const index = method.bands.findIndex(band => band.grade === grade);
  if (index < 0) return "—";
  const band = method.bands[index];
  const upper = method.bands[index - 1]?.min_z;
  return band.min_z === null ? `z < ${upper}`
    : upper == null ? `z ≥ ${band.min_z}` : `${band.min_z} ≤ z < ${upper}`;
}

export function gradeExplanation(dimension: string, grade: string, score: number | null | undefined, method: GradeMethod | undefined, zh: boolean): string {
  const value = typeof score === "number" && Number.isFinite(score) ? `z = ${score.toFixed(3)}`
    : score === undefined ? (zh ? "该快照未记录分值" : "Score not recorded in this snapshot")
    : (zh ? "不可评级：有效成员／样本／截面差异不足，或该股票缺少成员" : "Not gradeable: insufficient live members, observations, spread, or ticker members");
  return `${dimension} · ${grade} · ${gradeBand(grade, method)} · ${value}`;
}
