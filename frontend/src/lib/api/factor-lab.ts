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

// Phase B2: the skeptic pass's risk annotation on a survivor.
export interface SkepticVerdict {
  risk_level: "low" | "medium" | "high";
  concerns: string[];
  summary: string;
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
  // Phase B: self-correlation gate + skeptic pass. Optional — absent on
  // proposals created before Phase B shipped.
  self_correlation?: number;
  self_correlation_with?: string | null;
  skeptic?: SkepticVerdict | null;
}

// Phase A/B: one mining-journal lesson (KEEP / WEAK / AVOID) shown in the
// Mining Journal panel.
export interface MiningLesson {
  created_at: string | null;
  expression: string;
  outcome: "accepted" | "weak" | "rejected";
  test_sharpe: number | null;
  test_ic: number | null;
  deflated_sharpe: number | null;
  reject_reason: string | null;
  lesson: string;
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

// Phase D async refactor: POST returns 202 with a job_id; client polls
// GET /jobs/{id} until status reaches a terminal value (done | failed).
export type ProposeJobStatus = "queued" | "running" | "done" | "failed";

export interface ProposeJobAcceptedResponse {
  job_id: string;
  status: "queued" | "done";
  // Cost-guard short-circuit returns 'done' inline so the client skips
  // the poll loop entirely when the result is already known.
  inline_result?: ProposeResult;
}

export interface ProposeJobRow {
  id: string;
  user_id: number;
  status: ProposeJobStatus;
  n: number;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  result: ProposeResult | null;
  error: string | null;
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

export const fetchMiningLessons = (limit = 20, opts?: ApiGetOptions) =>
  apiGet<{ lessons: MiningLesson[] }>(
    `/api/factor-lab/lessons?limit=${limit}`,
    opts,
  );

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

// Phase D: POST now returns 202 with a job_id (or 'done' + inline_result
// for the cost-guard short-circuit). Callers should chain into
// pollProposeJob() to drive UI to terminal state.
export const proposeFactors = (n = 5) =>
  apiPost<ProposeJobAcceptedResponse, { n: number }>(
    "/api/factor-lab/propose",
    { n },
  );

export const getProposeJob = (jobId: string) =>
  apiGet<ProposeJobRow>(`/api/factor-lab/jobs/${jobId}`);

export interface PollProposeJobOptions {
  intervalMs?: number;       // 3000 default — every 3 seconds
  maxAttempts?: number;      // 100 default — 5min wall-clock budget
  onUpdate?: (row: ProposeJobRow) => void;
  signal?: AbortSignal;
}

export class ProposeJobTimeout extends Error {
  constructor(public lastRow: ProposeJobRow | null) {
    super("propose job did not reach terminal state within budget");
  }
}

/**
 * Poll a propose job until terminal state. Returns the final row; throws
 * ProposeJobTimeout if the budget is exhausted (UI offers retry).
 * Cancellable via AbortSignal so component unmount stops polling.
 */
export async function pollProposeJob(
  jobId: string,
  opts: PollProposeJobOptions = {},
): Promise<ProposeJobRow> {
  const intervalMs = opts.intervalMs ?? 3000;
  const maxAttempts = opts.maxAttempts ?? 100;
  let lastRow: ProposeJobRow | null = null;
  for (let i = 0; i < maxAttempts; i++) {
    if (opts.signal?.aborted) {
      throw new DOMException("polling aborted", "AbortError");
    }
    const row = await getProposeJob(jobId);
    lastRow = row;
    opts.onUpdate?.(row);
    if (row.status === "done" || row.status === "failed") {
      return row;
    }
    // Backoff sleeper that's interruptable by abort signal.
    await new Promise<void>((resolve, reject) => {
      const t = setTimeout(resolve, intervalMs);
      opts.signal?.addEventListener(
        "abort",
        () => {
          clearTimeout(t);
          reject(new DOMException("polling aborted", "AbortError"));
        },
        { once: true },
      );
    });
  }
  throw new ProposeJobTimeout(lastRow);
}

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
