# Benchmark Operator Output Requirements

**Version:** 0.1 Draft  
**Date:** 2026-06-19  
**Status:** Proposed  
**Owner:** StartD8 SDK  
**Primary entry points:** `scripts/run_flagship_benchmark.py`, `scripts/run_ob_benchmark.py`,
`scripts/run_behavioral_pilot.py`

## 1. Purpose

Benchmark execution can spend real provider budget and may run for many minutes per cell. Today the
operator sees a preflight estimate, then only one summary line after a cell completes. The nested
`run_prime_workflow.py` process is captured by the matrix runner, so its lifecycle and diagnostics are
not visible while the cell is in progress. A process interruption can also leave useful generated
artifacts on disk without an updated run-level result file.

This capability provides a concise terminal experience, an optional machine-readable event stream,
and durable incremental checkpoints. It does not change generation, scoring, provider selection,
or the benchmark result semantics.

## 2. Scope and Boundaries

This work is local operator experience and durable run artifacts. It is distinct from
`docs/design/benchmark-observability-tracking/REQUIREMENTS.md`, which specifies ContextCore/Loki
tracking and dashboards. Neither capability may require the other.

In scope:

- Terminal output for benchmark lifecycle, per-cell progress, budget consumption, result summaries,
  and artifact locations.
- Optional live relay of nested workflow output.
- Append-only local progress events and atomically replaced run checkpoints.
- Redaction and bounded retention of child-process diagnostics.

Out of scope:

- Changing model prompts, scoring formulas, retry policy, seed selection, or budget rules.
- New provider streaming APIs or token-by-token model output.
- ContextCore, Loki, Grafana, or remote telemetry changes.
- Resume scheduling. Checkpoints make partial results inspectable; they do not decide what to rerun.

## 3. Operator Modes

- **FR-1 Default concise terminal mode.** Every benchmark CLI MUST default to human-readable,
  line-oriented lifecycle output. It MUST work when stdout is redirected and MUST NOT require Rich or
  a TTY.
- **FR-2 Quiet mode.** Each CLI MUST provide `--quiet` to suppress progress lines while preserving
  fatal errors and the final artifact location on stderr. This supports scripts that need the current
  low-noise behavior.
- **FR-3 Verbose workflow mode.** Each CLI MUST provide `--verbose` (or an equivalent common flag)
  that relays redacted nested-workflow stdout and stderr to the terminal as lines arrive. Each line
  MUST be prefixed with the stable cell identity and stream (`stdout` or `stderr`).
- **FR-4 JSON event mode.** Each CLI MUST provide `--json-events <path|->`. It MUST write one JSON
  object per line in event order. `-` writes JSON events to stdout; in that mode, human-readable
  progress MUST use stderr so the JSON stream remains parseable.

## 4. Lifecycle Visibility

- **FR-5 Run preflight.** Before a model call, output MUST include run name/id, selected services and
  models, repetitions, total cells, behavioral-scoring state, configured budget ceiling, estimated
  cost, and output directory. Any missing pricing or unavailable local prerequisite MUST be named.
- **FR-6 Cell start.** Before launching a cell, output MUST include ordinal/total, stable `cell_id`,
  service, model, repetition, tier, workdir, and per-cell cost cap when one applies.
- **FR-7 Stage transitions.** The runner MUST emit stage transitions for at least `generation`,
  `generation_complete`, `compile_scoring`, `behavioral_provisioning`, `behavioral_execution`, and
  `completed`. Stages that do not apply MUST be omitted, not fabricated.
- **FR-8 Heartbeat.** While a child workflow is running, concise mode MUST emit an elapsed-time
  heartbeat no less often than every 60 seconds. The heartbeat MUST identify the cell and stage but
  MUST NOT claim token progress that the provider has not reported.
- **FR-9 Cell completion.** Each completed cell MUST report status, elapsed time, actual cost when
  available, structural quality, compile outcome, functional coverage or degradation reason, and the
  cumulative spend and remaining budget. A non-OK status MUST include a concise, redacted reason.
- **FR-10 Final summary.** On normal completion, budget exhaustion, keyboard interruption, or an
  uncaught runner failure, output MUST state completed/total cells, status counts, cumulative cost,
  output directory, and all known report/checkpoint paths.

## 5. Event and Checkpoint Artifacts

- **FR-11 Event schema.** Every lifecycle message MUST be represented as a structured event with at
  least `timestamp`, `run_id`, `event`, `stage`, and `message`. Cell-scoped events MUST also carry
  `cell_id`, `service`, `model`, and `repetition`. Completion events MUST carry the available result
  fields rather than requiring consumers to parse terminal text.
- **FR-12 Event persistence.** When event output is enabled, write an append-only
  `operator-events.jsonl` under the run output directory. A process interrupted after a flushed event
  MUST leave earlier events readable. The final event MUST be `run_completed`, `run_interrupted`, or
  `run_failed`.
- **FR-13 Incremental checkpoints.** After every terminal cell outcome, atomically update
  `cells.json`, `aggregate.json`, and `progress.json`. `progress.json` MUST contain run identity,
  completed/total cells, per-status counts, actual spend, remaining budget when calculable, and the
  latest event timestamp. A partial run MUST therefore be inspectable without reconstructing it from
  child workdirs.
- **FR-14 Existing artifact compatibility.** The established `run-spec.json`, `cells.json`,
  `aggregate.json`, and `leaderboard.md` shapes remain backward-compatible. Additive fields are
  allowed; field removal or semantic reinterpretation is not.
- **FR-15 Artifact inventory.** Final output and `progress.json` MUST list the primary reports and
  relevant per-cell workdir. It MAY link to debug logs only when those logs were written.

## 6. Child Process and Diagnostic Handling

- **FR-16 Streaming seam.** Extend the shared child-process execution helper with an optional output
  callback. Existing callers without a callback MUST retain their current capture-and-return behavior.
- **FR-17 Concurrent streams.** The helper MUST drain stdout and stderr concurrently. A verbose child
  process must not block because one pipe fills while the other is being read.
- **FR-18 Bounded tails.** Preserve separate bounded stdout and stderr tails for status classification
  and post-run diagnostics. The default retention limit MUST be documented and independently testable.
- **FR-19 Diagnostic availability.** A degraded behavioral result MUST expose the available readiness,
  network-isolation, missing-module, attempted-proto-path, server-stderr-tail, and connect-error
  fields to completion events and `cells.json` without altering scoring behavior.

## 7. Safety and Reliability

- **FR-20 Redaction.** Terminal lines, JSON events, and persisted child-process tails MUST pass
  through the repository redaction utility before emission. API keys, bearer tokens, known secret
  environment values, and user home paths MUST not be written to terminal events or run artifacts.
- **FR-21 No raw prompts by default.** Prompt bodies, raw model responses, and unbounded child output
  MUST NOT be persisted or printed in concise mode. Verbose relay is live-only unless an explicit
  future capture feature is approved.
- **FR-22 Non-interference.** Rendering terminal output, JSON events, and checkpoints MUST NOT alter
  a cell's status, quality, functional coverage, cost accounting, timeout, or sandbox settings. An
  output/checkpoint failure MUST be reported as an operator-output warning and MUST NOT turn a
  successful model cell into a failed benchmark result.
- **FR-23 Bounded overhead.** Concise mode may not poll providers. It may use a local timer for the
  heartbeat. Event and checkpoint writes MUST be bounded and use atomic file replacement; a slow or
  failing output sink must not materially delay the generation/scoring critical path.

## 8. Acceptance Criteria

1. A one-cell dry run prints a preflight containing all FR-5 fields and makes no model call.
2. A fixture child that writes alternately to stdout and stderr can be relayed in verbose mode without
   deadlock; the captured tails remain separate and bounded.
3. A one-cell successful fixture prints start, stages, completion, cumulative budget, and final paths;
   `operator-events.jsonl` parses line by line and ends in `run_completed`.
4. A behavioral degradation prints and persists a named reason while retaining the original benchmark
   status and score semantics.
5. Interrupting after one of two fixture cells leaves valid atomic `cells.json`, `aggregate.json`, and
   `progress.json` containing the completed cell.
6. A synthetic secret and home path are absent from text output, events, and stored tails.
7. Existing unit tests that call the child-process helper without an output callback retain their
   current return contract.

## 9. Open Decisions

- **OQ-1:** Should `--json-events` default to a run-local file, or remain explicit to avoid creating
  an additional artifact for every legacy run? Recommendation: default it on for `--run`, with
  `--quiet` affecting only terminal text.
- **OQ-2:** Should verbose workflow lines be persisted after redaction? Recommendation: no; retain
  only bounded tails unless a separate evidence-retention requirement defines access controls and
  storage limits.
- **OQ-3:** Should the existing CLI `--progress` flag on `run_prime_workflow.py` be forwarded by the
  matrix runner? Recommendation: not initially. The parent lifecycle renderer is deterministic and
  TTY-independent; forward it only after confirming Rich rendering is useful through a pipe.
