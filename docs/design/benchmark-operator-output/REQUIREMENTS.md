# Benchmark Operator Output Requirements

**Version:** 0.1 Draft  
**Date:** 2026-06-19  
**Status:** Proposed  
**Primary entry points:** `run_flagship_benchmark.py`, `run_ob_benchmark.py`, and
`run_behavioral_pilot.py`

## Purpose and Scope

Benchmark cells can spend provider budget and run for many minutes. The current matrix CLIs print a
preflight and a terminal result line, while the nested workflow output is captured until the cell exits.
Interrupted runs can leave generated workdirs without an up-to-date run-level result.

This capability adds local terminal UX and durable local run artifacts. It is independent of the
ContextCore/Loki tracking requirements in `benchmark-observability-tracking`; it changes neither model
prompts, scoring, provider selection, retry policy, nor remote telemetry.

## Functional Requirements

- **FR-1 Concise mode.** Benchmark CLIs MUST default to line-oriented lifecycle output that works with
  redirected stdout and without a TTY or Rich.
- **FR-2 Quiet mode.** `--quiet` MUST suppress progress while retaining fatal errors and final artifact
  locations on stderr.
- **FR-3 Verbose mode.** `--verbose` MUST relay redacted nested workflow stdout/stderr as lines arrive,
  prefixed with stable cell identity and stream name.
- **FR-4 JSON events.** `--json-events <path|->` MUST write newline-delimited JSON events. With `-`,
  stdout is JSON only and human output moves to stderr.
- **FR-5 Preflight.** Before a model call print run id, services, models, repetitions, cell count,
  behavioral state, budget ceiling, estimate, output directory, missing pricing, and prerequisites.
- **FR-6 Cell lifecycle.** Emit cell start with ordinal, identity, tier, workdir and cap; then emit
  applicable `generation`, `generation_complete`, `compile_scoring`, `behavioral_provisioning`,
  `behavioral_execution`, and terminal stages.
- **FR-7 Heartbeat.** While generation is active, concise mode MUST print an elapsed-time heartbeat at
  least every 60 seconds. It MUST not invent token progress.
- **FR-8 Completion.** Report status, elapsed time, actual cost, structural quality, compile outcome,
  functional coverage or named degradation reason, cumulative spend, and remaining budget.
- **FR-9 Final summary.** Normal completion, budget exhaustion, interruption, and runner failure MUST
  report completed/total cells, status counts, spend, output directory, and known artifact paths.

## Event and Artifact Requirements

- **FR-10 Event schema.** Every lifecycle message MUST have `timestamp`, `run_id`, `event`, `stage`,
  and `message`; cell events also have `cell_id`, service, model, and repetition. Completion events
  carry available result fields.
- **FR-11 Event persistence.** When enabled, append events to `operator-events.jsonl` in the run
  directory. The last event is `run_completed`, `run_interrupted`, or `run_failed`.
- **FR-12 Checkpoints.** After each terminal cell, atomically replace `cells.json`, `aggregate.json`,
  and `progress.json`. `progress.json` records run identity, completed/total, status counts, spend,
  remaining budget where calculable, and latest timestamp.
- **FR-13 Compatibility.** Existing `run-spec.json`, `cells.json`, `aggregate.json`, and
  `leaderboard.md` remain backward compatible; additions only.
- **FR-14 Artifact inventory.** Final output and `progress.json` list reports, checkpoints, and the
  relevant workdir.

## Child Process and Safety Requirements

- **FR-15 Streaming seam.** The shared child-process helper gains an optional output callback; callers
  without it retain capture-and-return behavior.
- **FR-16 Concurrent drains.** Stdout and stderr MUST be drained concurrently; verbose output cannot
  deadlock when either pipe fills.
- **FR-17 Bounded diagnostics.** Preserve separate, documented, bounded stdout/stderr tails for status
  classification and diagnostics.
- **FR-18 Behavioral diagnostics.** Completion events and `cells.json` expose available readiness,
  isolation, missing-module, attempted-proto-path, server stderr, and connect-error fields without
  changing scoring.
- **FR-19 Redaction.** Terminal text, JSON events, and persisted tails pass through repository
  redaction. API keys, bearer tokens, known secret values, and home paths are never emitted.
- **FR-20 No raw prompts.** Concise output and default artifacts do not print or persist prompt bodies,
  raw model responses, or unbounded child output. Verbose relay is live-only.
- **FR-21 Non-interference.** Output or checkpoint failures generate warnings and never change cell
  status, scoring, cost, timeout, or sandbox behavior.
- **FR-22 Bounded overhead.** No provider polling. Heartbeats use local time; output writes are bounded
  and atomic.

## Acceptance Criteria

1. A one-cell dry run prints all preflight fields and calls no model.
2. A fixture child interleaving stdout and stderr streams without deadlock; tails stay distinct/bounded.
3. A successful fixture writes valid JSONL ending in `run_completed` and atomic checkpoints after its
   terminal cell.
4. A degraded behavioral cell persists its named reason without altered score/status semantics.
5. Interrupting after one of two fixture cells leaves readable partial `cells.json`, `aggregate.json`,
   and `progress.json`.
6. Synthetic secrets and home paths are absent from text, events, and stored tails.

## Open Decisions

- Make run-local JSONL default for paid runs, or require `--json-events` explicitly. Recommendation:
  default on for paid runs.
- Do not persist verbose workflow output without a separate retention/access-control design.
- Do not forward the child workflow's Rich `--progress` until its behavior through pipes is proven;
  parent lifecycle output is the initial deterministic interface.
