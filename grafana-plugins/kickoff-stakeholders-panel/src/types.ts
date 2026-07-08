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
