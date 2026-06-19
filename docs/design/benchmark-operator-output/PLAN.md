# Benchmark Operator Output Implementation Plan

**Companion:** `REQUIREMENTS.md`  
**Status:** Proposed  
**Scope:** local benchmark CLI output and artifacts; no scoring or provider changes

## 1. Design

Introduce a small operator-output layer rather than embedding terminal formatting in the matrix
executor:

- `OperatorEvent`: an additive structured event model and text renderer.
- `OperatorOutput`: emits concise text, optional JSONL, warnings, and atomic checkpoints.
- `run_command(..., on_output=...)`: optional child-output seam that preserves existing callers.
- Runner lifecycle callbacks: start/stage/completion events without making the result model depend on
  a terminal.

The runner remains authoritative for `CellResult`; operator output observes it. Output failures are
reported and isolated from benchmark status calculation.

## 2. Work Items

### O1 — Event model and renderer

Create `src/startd8/benchmark_matrix/operator_output.py` with:

- A JSON-serializable `OperatorEvent` dataclass.
- Stable event names: `run_started`, `cell_started`, `stage_changed`, `cell_completed`,
  `operator_warning`, `run_completed`, `run_interrupted`, `run_failed`.
- A concise line renderer with an injectable clock for tests.
- Redaction before both text and JSON serialization.

**Verify:** unit-test event shape, text routing (`stdout` vs `stderr`), redaction, and no secret
fields in serialized output.

### O2 — Concurrent child-process streaming

Extend `src/startd8/model_comparison.py:run_command` with an optional callback receiving stream name
and line. Implement `Popen` plus concurrent pipe readers, a bounded tail buffer per stream, timeout
termination, and the current return dictionary shape.

Do not enable streaming for an existing caller unless it supplies the callback.

**Verify:** fixture process interleaves enough stdout/stderr to fill a pipe; the call completes,
callbacks preserve stream identity, tails are bounded, timeout behavior remains classified.

### O3 — Matrix lifecycle and checkpoints

Extend `SubprocessCellExecutor` and `run_matrix` with optional observer hooks. Emit stages around the
existing generation, compilation/scoring, behavioral provisioning/execution, and terminal result.

Add a run-state writer invoked after each terminal cell to atomically write:

- `cells.json`
- `aggregate.json`
- `progress.json`

Write `operator-events.jsonl` only when event output is enabled. Maintain additive artifact shapes.

**Verify:** a two-cell fake executor leaves a valid checkpoint after cell one; forced interruption
after cell one produces `run_interrupted`; output-writer exceptions produce warnings but do not alter
the successful cell result.

### O4 — CLI adoption

Add common flags to:

- `scripts/run_flagship_benchmark.py`
- `scripts/run_ob_benchmark.py`
- `scripts/run_behavioral_pilot.py`

Flags: `--quiet`, `--verbose`, `--json-events <path|->`. Default concise output is enabled for real
runs and dry runs. In `--json-events -` mode, reserve stdout for JSON and send text to stderr.

The flagship runner should render behavioral degradation fields explicitly, including the named
reason and relevant workdir/artifact path.

**Verify:** CLI unit tests cover dry-run, quiet, JSON-stdout, malformed event path, and final artifact
inventory. Keep current budget fail-closed behavior unchanged.

### O5 — Documentation and operational rehearsal

Document output modes, artifact locations, and interruption behavior in the benchmark CLI help text
and relevant benchmark design README. Run a no-spend dry run and a local fake-executor integration
test. Then run one credentialed, budget-capped real cell only after operator confirmation.

**Verify:** captured terminal transcript demonstrates the lifecycle sequence; JSONL validates one
object per line; no raw prompt or secret appears in the transcript or artifacts.

## 3. Sequencing

1. O1 and O2 establish testable, reusable seams.
2. O3 wires lifecycle events and makes partial results durable.
3. O4 exposes the behavior uniformly to operators.
4. O5 validates usability on a real bounded run.

O3 depends on O1. O4 depends on O1 and O3. O2 can land independently, but must be complete before
verbose nested workflow relay is exposed in O4.

## 4. Risk Controls

| Risk | Control |
|---|---|
| Streaming changes child timeout/error behavior | Preserve the default capture-only path; add timeout and interleaved-stream regression tests. |
| Terminal output leaks provider secrets | Redact at the operator-output boundary; never emit prompts/raw responses in concise mode. |
| Checkpoint I/O damages a valid run | Atomic replace, warning-only failures, and no mutation of `CellResult`. |
| JSON consumers receive mixed text | In `--json-events -` mode write all human text to stderr. |
| Output becomes noisy for large matrices | Concise default, `--quiet` opt-out, verbose child relay only by explicit flag. |

## 5. Completion Criteria

- All acceptance criteria in `REQUIREMENTS.md` pass.
- Existing benchmark, scoring, and sandbox tests remain green.
- A one-cell real run demonstrates preflight, live lifecycle, completion metrics, durable checkpoints,
  and a redaction check without changing the cell's result relative to the pre-output baseline.
