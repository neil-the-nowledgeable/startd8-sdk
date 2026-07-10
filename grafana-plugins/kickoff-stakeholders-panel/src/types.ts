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
  /**
   * Which surface this panel shows: the paid single-question Q&A run, the FR-R7 apply gate, the
   * multi-round `facilitate` (fire-and-poll) facilitation, or `triage` (route a finished synthesis into
   * typed candidates + the paid extract → disposition → serialize write path). Default `run`.
   */
  mode?: 'run' | 'apply' | 'facilitate' | 'triage';
  /** Facilitate posture: `scrutiny` (strategic red-team) or `prototype` (constructive early-stage UX). */
  posture?: 'scrutiny' | 'prototype';
  /** Facilitate model tier: `premium` (opus/gpt-5.5/gemini-pro) or `cheap` (haiku/mini/flash). */
  tier?: 'premium' | 'cheap';
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
  /** #8 — consensus of the source facilitation (always present; label "n/a" when uncomputable). */
  consensus?: ConsensusSignal;
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

/** Facilitate dry-run preview (no spend) — mirrors facilitate_run.FacilitateDryRun.to_dict(). */
export interface FacilitateDryRunResult {
  run_key: string;
  posture: string;
  tier: string;
  n_participants: number;
  projected_calls: number;
  estimated_cost: number;
  models: Record<string, string>;
  note: string;
}

/** Confirmed facilitate spawn (fire-and-poll) — mirrors start_facilitation()'s return dict. */
export interface FacilitateStartResult {
  session_id: string;
  run_key: string;
  status: string; // "in_progress" | "completed" (deduped-to-terminal)
  deduped: boolean;
}

/**
 * Facilitate poll payload — mirrors facilitate_run.facilitate_status(). `is_terminal` gates the poll:
 * completed | cancelled | error are terminal; unknown means the transcript isn't visible yet.
 */
export interface FacilitateStatusResult {
  session_id: string;
  status: string; // "in_progress" | "completed" | "cancelled" | "error" | "unknown"
  posture?: string;
  tier?: string;
  rounds_completed?: number;
  cost_so_far_usd?: number;
  synthesis?: string;
  /** #6 — synthetic lexical-divergence signal over the independent R1 answers (see ConsensusView). */
  consensus?: ConsensusSignal;
  /** #7 — per-round summaries that grow as rounds land (excerpt-bounded; live progress). */
  rounds?: RoundSummary[];
  /** #9 — heuristic: no transcript progress in ~N min (the worker may have died). Not terminal. */
  stalled?: boolean;
  halt?: string | null;
  is_terminal?: boolean;
  error?: string;
}

/** #7 — one persona's bounded contribution within a round. */
export interface RoundEntry {
  role_id: string;
  display_name: string;
  excerpt: string; // first N chars of the text (+ ellipsis) — not the full contribution
  grounding: string;
  is_challenger: boolean; // adversary/skeptic — prompted to diverge
}

/** #7 — one facilitation round's live summary (mirrors facilitate_run._round_summaries). */
export interface RoundSummary {
  round_id: string;
  title: string;
  kind: string;
  entries: RoundEntry[];
}

/** Consensus signal — mirrors stakeholder_panel.consensus.ConsensusResult.to_dict(). */
export interface ConsensusSignal {
  label: 'high' | 'mixed' | 'low' | 'n/a';
  score: number | null; // null when n/a
  n: number; // rateable (non-challenger) personas
  basis: string; // the scorer, e.g. "lexical-r1"
}

// ─────────────────────────────── Triage mode (synthesis → write path) ───────────────────────────────

/** One triaged synthesis item — mirrors synthesis_bridge Candidate.to_dict(). */
export interface TriageCandidate {
  title: string;
  source_section: string;
  raw_text: string;
  lane: 'FIELD_LEVEL' | 'NON_DECIDABLE' | 'UNSTRUCTURED';
  reason: string;
  suggested_owner: string;
  value_path: string | null;
  input_kind: string;
  role: string;
}

/** Triage report — mirrors TriageReport.to_dict() + the M1a `backlog_markdown` + `synthesis_present`. */
export interface TriageReportResult {
  kind: string;
  session_id: string;
  counts: Record<string, number>; // per-lane + total
  kind_counts: Record<string, number>; // per input_kind
  health: string[];
  candidates: TriageCandidate[];
  synthesis_present: boolean;
  backlog_markdown: string; // "" when no candidates (M1a)
}

/** Extract dry-run (no spend) — mirrors the `_extract` dry_run response. */
export interface ExtractDryRun {
  session_id: string;
  synthesis_checksum: string;
  extract_key: string;
  estimated_cost: number;
  model: string;
  n_allowed: number;
  note: string;
}

/** One staged field-level rec — carries `domain` (M1b) so a disposition call can be built from it. */
export interface StagedRow {
  domain: string;
  value_path: string;
  value: string;
}

/** Extract confirm result — `staged` or idempotent `deduped` (which omits the cost fields, FR-8b). */
export interface ExtractResult {
  session_id: string;
  status: 'staged' | 'deduped';
  staged: StagedRow[];
  synthesis_checksum: string;
  actual_cost?: number; // absent on the `deduped` branch — do NOT bind blindly (FR-8b)
  input_tokens?: number;
  output_tokens?: number;
  ceiling_exceeded?: boolean;
  note?: string;
}

/** Disposition result — mirrors the `_disposition` response. */
export interface DispositionResult {
  session_id: string;
  domain: string;
  value_path: string;
  disposition: 'accepted' | 'rejected';
  updated: boolean;
}

/** Serialize result — `rejected` is a list of `[value_path, reason]` tuples (FR-10a). */
export interface SerializeResult {
  staged: string[];
  rejected: Array<[string, string]>;
  inbox: string | null;
}
