// WorldQuant BRAIN credential vault client (Phase E2). The password is only ever
// sent on save; the status/test endpoints never return it.
import { apiGet, apiPost, type ApiGetOptions } from "./client";

export interface BrainStatus {
  connected: boolean;
  username_last4?: string;
  saved_at?: string | null;
}

export interface BrainTestResult {
  ok: boolean;
  error?: string;
}

export const fetchBrainStatus = (opts?: ApiGetOptions) =>
  apiGet<BrainStatus>("/api/brain/credentials", opts);

export const saveBrainCredentials = (username: string, password: string) =>
  apiPost<
    { connected: boolean; username_last4: string },
    { username: string; password: string }
  >("/api/brain/credentials", { username, password });

export const testBrainConnection = () =>
  apiPost<BrainTestResult, Record<string, never>>(
    "/api/brain/credentials/test",
    {},
  );

// Phase E4/E5: one BRAIN mining result. Outcome buckets the candidate after it
// was simulated on the real platform.
export type BrainOutcome = "passed" | "flagged" | "rejected" | "sim_error";

export interface BrainAlpha {
  id: number;
  expression: string;
  // Economic family of the expression (options/value/lowvol/sentiment/
  // momentum/score/revision/other), classified server-side by family_of.
  // Optional: absent on responses served before the /alphas family tag shipped.
  family?: string | null;
  settings: Record<string, unknown>;
  alpha_id: string | null;
  sharpe: number | null;
  fitness: number | null;
  turnover: number | null;
  drawdown: number | null;
  returns: number | null;
  margin: number | null;
  self_correlation: number | null;
  self_correlation_with: string | null;
  self_correlation_status?:
    | "pending"
    | "ready"
    | "skipped_prerequisite"
    | "unavailable"
    | null;
  self_correlation_adj: number | null;
  self_correlation_adj_with: string | null;
  grade: string | null;
  fail_checks: string | null;
  retried: boolean;
  outcome: BrainOutcome;
  detail: string | null;
  created_at: string | null;
  submitted_at: string | null;
  brain_status: string | null;
  /** Round this row was mined in (DB clock at dispatch); groups the batch-divider UI. */
  batch_started_at: string | null;
  // Blend provenance (family_focus == "blend" rounds only): the parent expressions
  // this candidate was stitched from. null for every non-blend row, including all
  // rows recorded before this shipped (we do not retro-tag historical blends).
  // is_blend is derived server-side from blend_parents (never stored separately),
  // so it can never disagree with the parent list.
  blend_parents?: string[] | null;
  is_blend?: boolean;
  research_evidence?: {
    context_key?: string;
    hypothesis?: {
      id?: string;
      title?: string;
      source_url?: string | null;
      target?: string;
      confidence?: string;
      falsification?: string;
    };
    field_mapping?: {
      field_ids?: string[];
      dataset_ids?: string[];
      coverage?: number;
      mapped_ratio?: number;
    };
    semantic_audit?: {
      status?: "matched" | "mismatch" | "unverified";
      semantic_fidelity?: number;
      metadata_available?: boolean;
      required_semantics?: string[];
      matched_required_semantics?: string[];
      missing_required_semantics?: string[];
      material_mismatch?: boolean;
      high_confidence_mismatch?: boolean;
      target_outcome_alignment?: {
        target?: string;
        status?: "aligned" | "exploratory_mismatch" | "unknown";
        brain_default_target?: string;
      };
      field_details?: Array<{
        field_id?: string;
        name?: string;
        description?: string;
        dataset?: string;
        side?: string | null;
        measure_kind?: string;
        tenor?: string[];
      }>;
    };
    screen?: Record<string, string | number>;
    proxy?: {
      active?: boolean;
      sample_n?: number;
      reason?: string;
      validated_targets?: string[];
      prediction?: Record<string, number>;
    };
  } | null;
}

export interface BrainSubmitResult {
  ok: boolean;
  brain_status: string;
  alpha_id: string;
}

export interface BrainAlphaQuery {
  limit?: number;
  offset?: number;
  /** Restrict the result page to one mining run. Omitted for legacy/all-runs mode. */
  run_id?: number | null;
  outcome?: BrainOutcome | "";
  q?: string;
  sharpe_min?: number | null;
  fitness_min?: number | null;
  turnover_max?: number | null;
  submitted?: boolean | null;
  family?: string;
  sort?: string;
  descending?: boolean;
}

export interface BrainAlphaPage {
  alphas: BrainAlpha[];
  total: number;
}

export const fetchBrainAlphas = (query: BrainAlphaQuery = {}, opts?: ApiGetOptions) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  }
  return apiGet<BrainAlphaPage>(`/api/brain/alphas?${p.toString()}`, opts);
};

// A mining run is the navigation/provenance boundary for candidate rows. The
// fields are optional on the client because older deployments may omit one or
// more of the funnel/status fields while the runs endpoint rolls out.
export interface BrainMiningRun {
  id: number;
  source?: string | null;
  family_focus?: string | null;
  requested_n?: number | null;
  generation_target_n?: number | null;
  parent_run_id?: number | null;
  generated_n?: number | null;
  screened_n?: number | null;
  simulated_n?: number | null;
  persisted_n?: number | null;
  passed_n?: number | null;
  flagged_n?: number | null;
  rejected_n?: number | null;
  sim_error_n?: number | null;
  status?: string | null;
  screen_status?: string | null;
  screen_detail?: string | null;
  seed?: number | string | null;
  created_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  error_detail?: string | null;
}

export interface BrainRunsPage {
  runs: BrainMiningRun[];
  total: number;
}

export const fetchBrainRuns = (limit = 12, opts?: ApiGetOptions) =>
  apiGet<BrainRunsPage>(`/api/brain/runs?limit=${encodeURIComponent(String(limit))}`, opts);

export interface BrainRunCandidate {
  id: number;
  run_id: number;
  ordinal: number;
  expression: string;
  settings: Record<string, unknown>;
  mechanism?: string | null;
  evidence?: Record<string, unknown> | null;
  evidence_score?: number | null;
  llm_score?: number | null;
  llm_status?: string | null;
  selected: boolean;
  stage: string;
  status: string;
  reason_code?: string | null;
  reason_text?: string | null;
  alpha_row_id?: number | null;
  alpha_id?: string | null;
  simulation_outcome?: string | null;
  simulation_detail?: string | null;
  created_at?: string | null;
  screened_at?: string | null;
  simulated_at?: string | null;
  updated_at?: string | null;
}

export interface BrainRunCandidatePage {
  run_id: number;
  candidates: BrainRunCandidate[];
  total: number;
  limit: number;
  offset: number;
}

export interface BrainRunCandidateQuery {
  limit?: number;
  offset?: number;
  selected?: boolean | null;
  status?: string | null;
}

export const fetchBrainRunCandidates = (
  runId: number,
  query: BrainRunCandidateQuery = {},
  opts?: ApiGetOptions,
) => {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, String(value));
    }
  }
  const suffix = params.size > 0 ? `?${params.toString()}` : "";
  return apiGet<BrainRunCandidatePage>(
    `/api/brain/runs/${encodeURIComponent(String(runId))}/candidates${suffix}`,
    opts,
  );
};

export interface PnlPoint {
  date: string;
  pnl: number;
}

export const fetchAlphaPnl = (rowId: number, opts?: ApiGetOptions) =>
  apiGet<{ points: PnlPoint[] }>(`/api/brain/alphas/${rowId}/pnl`, opts);

export type YearlyRow = Record<string, string | number | null>;

export const fetchAlphaYearly = (rowId: number, opts?: ApiGetOptions) =>
  apiGet<{ rows: YearlyRow[] }>(`/api/brain/alphas/${rowId}/yearly`, opts);

export const submitBrainAlpha = (rowId: number) =>
  apiPost<BrainSubmitResult, Record<string, never>>(
    `/api/brain/alphas/${rowId}/submit`,
    {},
  );

export interface MineTriggerResult {
  ok: boolean;
  n_candidates: number;
  generation_target_n?: number | null;
  parent_run_id?: number | null;
  eta_minutes: number;
  // DB-clock anchor; the progress poller counts rows created after this.
  started_at: string;
  /** New run identity. Older backends may omit it, so callers must tolerate null. */
  run_id?: number | null;
}

export interface MineTriggerRequest {
  nCandidates: number;
  generationTarget: number;
  familyFocus?: string;
  parentRunId?: number | null;
  seed?: number;
}

export const triggerMining = ({
  nCandidates,
  generationTarget,
  familyFocus = "",
  parentRunId,
  seed,
}: MineTriggerRequest) =>
  apiPost<
    MineTriggerResult,
    {
      n_candidates: number;
      generation_target_n: number;
      family_focus: string;
      parent_run_id?: number;
      seed?: number;
    }
  >(
    "/api/brain/mine",
    {
      n_candidates: nCandidates,
      generation_target_n: generationTarget,
      family_focus: familyFocus,
      ...(parentRunId != null ? { parent_run_id: parentRunId } : {}),
      ...(seed != null ? { seed } : {}),
    },
  );

// Progress poll for an in-flight manual round. `mined` = candidates recorded since
// the dispatch anchor (real per-candidate count); `running` = GitHub Actions has a
// queued/in-progress run (authoritative completion signal), or null if GH is
// unavailable (the bar still fills from `mined`).
export interface MineStatus {
  running: boolean | null;
  latest_status: string | null;
  latest_conclusion: string | null;
  mined: number;
  run?: BrainMiningRun | null;
}

export const fetchMineStatus = (
  since: string,
  runId?: number | null,
  opts?: ApiGetOptions,
) => {
  const params = new URLSearchParams({ since });
  if (runId != null) params.set("run_id", String(runId));
  return apiGet<MineStatus>(
    `/api/brain/mine/status?${params.toString()}`,
    opts,
  );
};
