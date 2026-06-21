# Benchmark Operator Output Implementation Plan

**Companion:** `REQUIREMENTS.md`  
**Status:** Proposed

## Design

Create a small observer layer rather than coupling terminal formatting to benchmark scoring:

- `OperatorEvent`: JSON-serializable lifecycle data plus concise renderer.
- `OperatorOutput`: text, optional JSONL, warnings, and atomic checkpoints.
- Optional child-output callback on `run_command`.
- Optional runner lifecycle observer. `CellResult` remains authoritative.

Output failures are isolated from cell evaluation.

## Work Items

1. **Event model and renderer.** Add `benchmark_matrix/operator_output.py` with stable event types
   (`run_started`, `cell_started`, `stage_changed`, `cell_completed`, `operator_warning`, terminal run
   event), redaction, and stdout/stderr routing. Test schema and redaction.
2. **Concurrent child streaming.** Extend `model_comparison.run_command` using `Popen`, concurrent pipe
   readers, bounded separate tails, callback delivery, and preserved timeout/return contracts. Test an
   interleaved fixture and timeout.
3. **Lifecycle and checkpoints.** Add optional observer hooks to `run_matrix` and
   `SubprocessCellExecutor`; emit stages around generation, scoring, and behavior. Atomically update
   `cells.json`, `aggregate.json`, and `progress.json` after every terminal cell. Test interruption and
   writer failure isolation.
4. **CLI adoption.** Add `--quiet`, `--verbose`, and `--json-events` to flagship, baseline, and
   behavioral-pilot CLIs. Preserve fail-closed budget behavior and JSON-only stdout mode.
5. **Operational rehearsal.** Document modes and artifact locations. Validate with dry run and local
   fake executor; perform one budget-capped real cell only after explicit approval.

## Risks and Controls

| Risk | Control |
|---|---|
| Child-stream handling changes timeout semantics | Keep capture-only default; regression-test timeout and return shape. |
| Output leaks secrets | Redact at event boundary; no prompts/raw responses in concise mode. |
| Checkpoint I/O damages an otherwise valid run | Atomic replace; warning-only failure path. |
| JSON is polluted by terminal text | Route human text to stderr with `--json-events -`. |
| Large runs become noisy | Concise default, `--quiet`, verbose relay opt-in. |

## Completion

All requirement acceptance criteria pass, existing benchmark/scoring/sandbox tests stay green, and a
real bounded cell demonstrates lifecycle output and durable checkpoints without changing its score.
