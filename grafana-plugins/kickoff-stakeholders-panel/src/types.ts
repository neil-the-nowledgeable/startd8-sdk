/**
 * Panel options for the StartD8 Kickoff Stakeholders panel.
 *
 * The bearer token is NEVER a panel option (it would be world-readable in the dashboard JSON, per
 * FR-2/S-3). Requests route through a Grafana **datasource proxy** whose secureJsonData holds the
 * token and adds it server-side. The panel only knows the datasource UID.
 */
export interface StakeholdersPanelOptions {
  /** UID of the datasource that proxies `/stakeholders/*` to the run endpoint (adds the token). */
  datasourceUid: string;
  /** Default cap (max personas queried). Empty = all. */
  defaultCap?: number;
  /** Which surface this panel shows: the paid Q&A run, or the FR-R7 apply gate. Default `run`. */
  mode?: 'run' | 'apply';
}

/** One proposal the apply gate WOULD write — mirrors an item of PreviewResult.would_apply. */
export interface WouldApplyItem {
  proposal_id: string;
  kind: string;
  value_path?: string | null;
  params?: Record<string, unknown>;
}

/** FR-R7 preview response — the would-apply set + the single-use HMAC challenge. */
export interface ApplyPreviewResult {
  would_apply: WouldApplyItem[];
  envelope_seq: number;
  content_hash: string;
  challenge: string;
  expires_in_seconds: number;
  posture: string;
}

/** One per-proposal apply outcome — mirrors ApplyResult.outcomes[]. */
export interface ApplyOutcome {
  proposal_id: string;
  decision: string;
  code: string;
  ok?: boolean;
  detail?: string;
}

/** FR-R7 ratify response — mirrors ApplyResult.to (wrote/actionable/outcomes/shredded). */
export interface ApplyResultView {
  wrote: number;
  actionable: number;
  outcomes: ApplyOutcome[];
  inbox_shredded: boolean;
  stale: boolean;
  refused_reason: string;
}

/** Dry-run preview (no spend) — mirrors stakeholder_run.DryRun.to_dict(). */
export interface DryRunResult {
  run_key: string;
  roster_version: string;
  n_personas: number;
  per_question_estimate: number;
  estimated_cost: number;
  model: string;
  note: string;
}

/** One persona's synthetic, unratified answer — mirrors PanelAnswer.to_dict(). */
export interface PanelAnswerView {
  role_id: string;
  grounding: string;
  text: string;
}

/** Confirmed-run result — mirrors stakeholder_run.RunResult.to_dict(). */
export interface RunResult {
  session_id: string;
  status: string; // "completed" | "deduped" | "partial" | "cancelled"
  run_key: string;
  answers: PanelAnswerView[];
  note?: string;
}
