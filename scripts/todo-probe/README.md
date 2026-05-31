# TODO-completion probe (A/B/C)

A canonical fixture + harness that validates the post-generation TODO completion
path (`validators/todo_scanner.py` → `seeds/todo_derivation.py`) end-to-end using
the **real production functions** the pipeline calls in
`PrimeContractorWorkflow._run_todo_scan_and_inject()`.

It exists because most pipeline runs produce **no natural TODO stubs**, so there
is nothing to exercise the three categories. The probe supplies one of each:

| Category | Probe function | Handling |
|---|---|---|
| **A** uncomment | `configure_retry_policy()` | commented-out block restored deterministically ($0) |
| **B** implement | `init_metrics()` | instrumentation-init stub → derived as an `implement` task (routes to LLM) |
| **C** generic | `parse_config()` | detected but **not** injected (filtered out of the A/B task list) |

## Why this exists / what it guards

Two scanner bugs previously made TODO completion silently inert:

1. `scan_directory()` excluded any `/run-NNN-/` path — i.e. the current run's own
   output — so the scan found zero files.
2. Java/Go instrumentation-init stubs with guard/logging boilerplate classified as
   Category C and were dropped by the A/B-only injection filter.

Both are fixed in `todo_scanner.py`; this probe is the closed-loop validation.

## Usage

```bash
# From the SDK repo (venv auto-sourced if present):
scripts/todo-probe/validate.sh <path>

#   <path> may be:
#     • a plan-ingestion/generated dir
#     • a run-NNN-… dir
#     • a pipeline-output/<project> dir (newest run auto-picked)

# Example — validate against the newest run of a project's pipeline output:
scripts/todo-probe/validate.sh ~/Documents/dev/strtd8/strtd8/.cap-dev-pipe/pipeline-output/startd8
```

Expected: 5/5 PASS, and the probe file is removed from the target afterward.

`run_probe.py <dir>` can also be invoked directly; it stops at task derivation +
the deterministic Category-A uncomment (it does **not** spend tokens implementing
Category B — that happens in a full pipeline run).
