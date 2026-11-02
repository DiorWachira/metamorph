// Typed client for the Metamorph API. Types mirror the Pydantic models in
// src/metamorph/reports/model.py, src/metamorph/storage/repo.py and src/metamorph/server/app.py.

export type Mode = "blocking" | "warning";
export type Status = "pass" | "violation" | "inconclusive" | "error" | "skipped";
export type Triage = "unreviewed" | "true_bug" | "false_alarm";
export type DiffOp = "equal" | "delete" | "insert";
export type Segment = [DiffOp, string];
export type Diff = { left: Segment[]; right: Segment[] };

export interface OutputView {
  sample_idx: number;
  text: string;
  latency_ms: number;
  cost_usd: number;
  cached: boolean;
  error: string | null;
}

export interface CaseView {
  id: number;
  run_id: string;
  relation_id: string;
  seed_id: string;
  variant: number;
  mode: Mode;
  status: Status;
  score: number | null;
  threshold: number;
  nominal_threshold: number | null;
  self_variance: number | null;
  detail: string;
  followup_note: string;
  source_input: Record<string, unknown>;
  followup_input: Record<string, unknown>;
  source_outputs: OutputView[];
  followup_output: OutputView;
  triage: Triage;
  note: string | null;
  excused_by_baseline: boolean;
}

export interface RelationSummary {
  id: string;
  mode: Mode;
  mode_source: string;
  description: string;
  transform: string;
  comparator: string;
  threshold: number | null;
  expected: string;
  cases: number;
  passed: number;
  violations: number;
  inconclusive: number;
  errors: number;
  skipped: number;
  excused: number;
}

export interface GateResult {
  passed: boolean;
  blocking_violations: number;
  blocking_cases: number;
  error_rate: number;
  too_many_errors: boolean;
  reasons: string[];
}

export interface UnstableInput {
  seed_id: string;
  comparator: string;
  self_agreement: number;
  threshold: number;
  relations: string[];
}

export interface RunReport {
  run: {
    id: string;
    started_at: string;
    finished_at: string | null;
    git_sha: string | null;
    status: string;
    total_cost_usd: number;
    stats: Record<string, number>;
    llm: { model: string; calls: number; cache_hits: number; failures: number } | null;
    budget: { limit_usd: number | null; spent_usd: number } | null;
    samples: number;
  };
  gate: GateResult | null;
  relations: RelationSummary[];
  cases: CaseView[];
  skipped: { relation_id: string; seed_id: string; reason: string }[];
  unstable_inputs: UnstableInput[];
  baseline_effect: { naive_violations: number; violations: number; excused: number };
}

export interface RunListItem {
  id: string;
  started_at: string;
  status: string;
  git_sha: string | null;
  total_cost_usd: number;
  cases: number;
  violations: number;
  blocking_violations: number;
  gate_passed: boolean | null;
}

export interface RelationStats {
  relation_id: string;
  reviewed: number;
  true_bugs: number;
  false_alarms: number;
  precision: number | null;
  learned_mode: Mode | null;
}

export interface CaseDetail {
  case: CaseView;
  output_diff: Diff;
  input_diff: Diff;
  changed_field: string | null;
  neighbours: { previous: number | null; next: number | null };
}

export interface RelationEntry {
  id: string;
  description: string;
  transform: string;
  comparator: string;
  tags: string[];
  enabled: boolean;
  mode: Mode;
  mode_source: string;
  llm: boolean;
  requirement: string | null;
  stats: RelationStats | null;
}

export interface Proposal {
  spec: {
    id: string;
    description: string;
    requirement: string | null;
    expected: "invariant" | "flips";
    transform: { name: string; params: Record<string, unknown> };
    comparator: { name: string; threshold: number | null; params: Record<string, unknown> };
  };
  rationale: string;
  status: "proposed" | "approved" | "rejected";
  source: string;
  model: string;
  mined_at: string;
}

export interface RelationsResponse {
  relations: RelationEntry[];
  min_reviewed: number;
  min_precision: number;
}

export interface Overview {
  project: string;
  target: string;
  relations_enabled: number;
  runs: number;
  latest: RunListItem | null;
  reviewed: number;
  true_bugs: number;
  false_alarms: number;
}

export interface LabResponse {
  changed: boolean;
  note: string;
  text: string;
  documents: string[];
  diff: Diff;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

/** The public demo has no server: it reads a frozen snapshot and cannot record anything. */
export const READ_ONLY = import.meta.env.VITE_SNAPSHOT === "1";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (READ_ONLY && init?.method) {
    throw new ApiError(403, "This is a read-only demo. Install Metamorph to use this for real.");
  }
  const url = READ_ONLY ? `${import.meta.env.BASE_URL}snapshot${path}.json` : path;
  const response = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      detail = (await response.json()).detail ?? detail;
    } catch {
      /* not JSON */
    }
    throw new ApiError(response.status, String(detail));
  }
  return (await response.json()) as T;
}

export const api = {
  overview: () => request<Overview>("/api/overview"),
  runs: () => request<RunListItem[]>("/api/runs"),
  run: (id: string) => request<RunReport>(`/api/runs/${encodeURIComponent(id)}`),
  case: (id: number) => request<CaseDetail>(`/api/cases/${id}`),
  relations: () => request<RelationsResponse>("/api/relations"),
  triage: (id: number, verdict: Triage, note: string | null) =>
    request<{ case: CaseView; stats: RelationStats }>(`/api/cases/${id}/triage`, {
      method: "POST",
      body: JSON.stringify({ verdict, note }),
    }),
  proposals: () => request<Proposal[]>("/api/proposals"),
  decide: (id: string, decision: "approve" | "reject") =>
    request<Proposal[]>(`/api/proposals/${encodeURIComponent(id)}/${decision}`, { method: "POST" }),
  lab: (body: {
    transform: string;
    params: Record<string, unknown>;
    text: string;
    documents: string[];
    seed: number;
  }) => request<LabResponse>("/api/lab/transform", { method: "POST", body: JSON.stringify(body) }),
};
