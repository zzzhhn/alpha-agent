// frontend/src/lib/api/factor-lab.ts
// Factor-Lab dashboard client (Phase 3d). Targets the /api/factor-lab backend
// router via apiGet/apiPost (full /api path), matching the evolution.ts convention.
// Auth is auto-injected by Next.js middleware on same-origin /api/* requests.
import { apiGet, apiPost, type ApiGetOptions } from "./client";

export interface FactorProposalOperator {
  name: string;
  signature: string;
  python_impl: string;
  doc: string;
}

export interface FactorProposalOperatorTestResult {
  name: string;
  passed: boolean;
  tests: Array<{ name: string; passed: boolean; detail: string }>;
}

export interface FactorProposalEvidence {
  sharpes: number[];
  ic_oos: number;
  deflated_sharpe: number;
  baseline_sharpe: number;
  n_folds: number;
  n_trials: number;
  llm_rationale: string;
  operator_test_results: FactorProposalOperatorTestResult[];
}

export interface FactorDiagnosticSnapshot {
  current_expression: string;
  weak_signal: string | null;
  weak_signal_ic: number | null;
  worst_fold_sharpe: number | null;
  worst_fold_window: [string, string] | null;
  symptom_summary: string;
}

export interface FactorProposal {
  id: number;
  status: "pending" | "approved" | "rejected";
  expression: string;
  new_operators: FactorProposalOperator[];
  evidence: FactorProposalEvidence;
  diagnostic: FactorDiagnosticSnapshot;
  created_at: string | null;
  decided_at: string | null;
  decided_by: number | null;
}

export interface ProposeResult {
  evaluated: number;
  proposed: number;
  dormant: boolean;
}

export interface ApproveResult {
  ok: boolean;
  applied: Record<string, string>;
  registered_operators: string[];
  refresh_error: string | null;
}

export interface RollbackResult {
  ok: boolean;
  reverted_to: string | null;
}

export const fetchFactorDiagnostic = (opts?: ApiGetOptions) =>
  apiGet<FactorDiagnosticSnapshot>("/api/factor-lab/diagnostic", opts);

export const fetchFactorProposals = (
  status?: "pending" | "approved" | "rejected",
  opts?: ApiGetOptions,
) =>
  apiGet<{ proposals: FactorProposal[] }>(
    status
      ? `/api/factor-lab/proposals?status=${status}`
      : "/api/factor-lab/proposals",
    opts,
  );

export const proposeFactors = (n = 5) =>
  apiPost<ProposeResult, { n: number }>("/api/factor-lab/propose", { n });

export const approveFactorProposal = (id: number) =>
  apiPost<ApproveResult, Record<string, never>>(
    `/api/factor-lab/proposals/${id}/approve`,
    {},
  );

export const rejectFactorProposal = (id: number) =>
  apiPost<{ ok: boolean }, Record<string, never>>(
    `/api/factor-lab/proposals/${id}/reject`,
    {},
  );

export const rollbackFactorProposal = (id: number) =>
  apiPost<RollbackResult, Record<string, never>>(
    `/api/factor-lab/proposals/${id}/rollback`,
    {},
  );

export interface SetLiveExpressionResult {
  expression: string;
  updated_at: string;
}

export const setLiveExpression = (expression: string) =>
  apiPost<SetLiveExpressionResult, { expression: string }>(
    "/api/factor-lab/live-expression",
    { expression },
  );
