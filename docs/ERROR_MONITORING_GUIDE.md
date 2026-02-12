# Error Monitoring Guide

**Version:** 0.4.0
**Last Updated:** 2026-02-12
**Audience:** Humans and AI Agents

---

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [The .startd8/ Error Directory](#the-startd8-error-directory)
4. [Watching Errors in Real Time](#watching-errors-in-real-time)
5. [Querying Past Errors](#querying-past-errors)
6. [Error Sources](#error-sources)
7. [Error File Schema](#error-file-schema)
8. [Structured Log File](#structured-log-file)
9. [Checkpoint Files](#checkpoint-files)
10. [Grafana / Loki Integration](#grafana--loki-integration)
11. [Programmatic Access](#programmatic-access)
12. [Recipes](#recipes)

---

## Overview

When a StartD8 workflow fails -- whether it is an Artisan Contractor phase timeout, a code-generation LLM returning empty output, or a registered workflow validation error -- the SDK persists a structured error record to disk so you can inspect what went wrong without digging through terminal scrollback.

There are three complementary layers:

| Layer | Location | Best for |
|-------|----------|----------|
| **Task error store** | `.startd8/task_errors/` | Per-error JSON files + rolling JSONL log. Queryable, greppable, newest-first. |
| **Structured log file** | `~/.startd8/logs/startd8.log` | Full JSON log stream (all levels). Good for `tail -f` and Loki shipping. |
| **Checkpoint files** | `.startd8/checkpoints/` | Per-phase status snapshots. Shows where a workflow stopped and what cost was incurred. |

All three are written automatically -- no flags to set, no config to change.


## Quick Start

Run a workflow (e.g. an Artisan Contractor run). If anything fails:

```bash
# See every error that was recorded, newest first
cat .startd8/task_errors/errors.jsonl | jq -r '"\(.timestamp) [\(.source)] \(.error_message)"'

# Or list the per-error JSON files
ls .startd8/task_errors/*/

# Tail the rolling JSONL as the workflow runs
tail -f .startd8/task_errors/errors.jsonl
```

That's it. Every phase failure, generation error, workflow timeout, and budget exceeded event writes to this directory automatically.


## The .startd8/ Error Directory

After a workflow that encountered errors, the project directory looks like:

```
.startd8/
├── checkpoints/                          # Artisan workflow checkpoints
│   └── artisan-PI-001.checkpoint.json
├── state/                                # Development phase state
│   ├── generation_results.json
│   └── artisan-implement-1707753600_state.json
└── task_errors/                          # Unified error store
    ├── errors.jsonl                      # Rolling append-only log (all errors)
    └── artisan-PI-001/                   # Per-workflow subdirectory
        ├── 20260212_143022_implement.json
        ├── 20260212_143025_implement_1.json
        └── 20260212_143101_workflow.json
```

### errors.jsonl

A single file where every error is appended as one JSON object per line. This is the fastest way to scan all errors across all workflows:

```bash
# Count errors by source
cat .startd8/task_errors/errors.jsonl | jq -r '.source' | sort | uniq -c | sort -rn

# Show only IMPLEMENT phase errors
cat .startd8/task_errors/errors.jsonl | jq 'select(.source == "implement")'

# Errors in the last hour (requires GNU date or gdate on macOS)
SINCE=$(date -u -v-1H +%Y-%m-%dT%H:%M 2>/dev/null || date -u -d '1 hour ago' +%Y-%m-%dT%H:%M)
cat .startd8/task_errors/errors.jsonl | jq --arg s "$SINCE" 'select(.timestamp > $s)'
```

### Per-error JSON files

Each error also gets its own file under `.startd8/task_errors/{workflow_id}/`. These are useful when you want to inspect a single failure in detail, including the full Python traceback:

```bash
# Pretty-print the most recent error for a workflow
ls -t .startd8/task_errors/artisan-PI-001/*.json | head -1 | xargs jq .
```


## Watching Errors in Real Time

### Option 1: tail the JSONL (simplest)

Open a second terminal while the workflow runs:

```bash
tail -f .startd8/task_errors/errors.jsonl | jq .
```

Each error appears as it is recorded. Press `Ctrl+C` to stop.

### Option 2: tail the structured log file

The SDK log file at `~/.startd8/logs/startd8.log` contains all log levels (DEBUG through CRITICAL) in JSON format. Filter to errors:

```bash
tail -f ~/.startd8/logs/startd8.log | jq 'select(.level == "ERROR" or .level == "CRITICAL")'
```

### Option 3: watch the filesystem

If you prefer file-count based monitoring:

```bash
watch -n 2 'ls .startd8/task_errors/*/*.json 2>/dev/null | wc -l'
```


## Querying Past Errors

### By workflow ID

```bash
# All errors for a specific workflow run
ls .startd8/task_errors/artisan-PI-001/
cat .startd8/task_errors/errors.jsonl | jq 'select(.workflow_id == "artisan-PI-001")'
```

### By error type

```bash
# All phase execution errors
cat .startd8/task_errors/errors.jsonl | jq 'select(.error_type == "PhaseExecutionError")'

# All generation errors
cat .startd8/task_errors/errors.jsonl | jq 'select(.error_type == "GenerationError")'

# All timeout errors
cat .startd8/task_errors/errors.jsonl | jq 'select(.error_message | test("timed? ?out"; "i"))'
```

### By phase

```bash
# All IMPLEMENT phase errors
cat .startd8/task_errors/errors.jsonl | jq 'select(.source == "implement")'

# All DESIGN phase errors
cat .startd8/task_errors/errors.jsonl | jq 'select(.source == "design")'
```

### Summary report

```bash
# One-liner error summary: count by source and type
cat .startd8/task_errors/errors.jsonl | \
  jq -r '"\(.source)\t\(.error_type)"' | \
  sort | uniq -c | sort -rn
```


## Error Sources

The `source` field in each error record tells you where the error originated:

| Source | Meaning |
|--------|---------|
| `plan` | PLAN phase (plan deconstruction, preflight) |
| `scaffold` | SCAFFOLD phase (directory creation, lessons discovery) |
| `design` | DESIGN phase (design documentation generation) |
| `implement` | IMPLEMENT phase (code generation via LLMChunkExecutor) |
| `test` | TEST phase (test construction, final testing) |
| `review` | REVIEW phase (quality review) |
| `finalize` | FINALIZE phase (final assembly, retrospective) |
| `generation` | Individual task/chunk code generation failure |
| `workflow` | Workflow-level error (timeout, budget exceeded, unexpected exception) |

For registered workflows (plan-ingestion, doc-review, etc.), the source is `workflow` and the `workflow_id` field identifies which workflow failed.


## Error File Schema

Each JSON error file contains:

```json
{
  "workflow_id": "artisan-PI-001",
  "source": "implement",
  "error_type": "PhaseExecutionError",
  "error_message": "LLM returned empty output after 3 retries",
  "timestamp": "2026-02-12T14:30:22.456789+00:00",
  "context": {
    "phase": "implement",
    "cost": 0.42,
    "duration_seconds": 12.5,
    "task_id": "PI-001",
    "target_file": "src/mylib/auth.py"
  },
  "traceback": "Traceback (most recent call last):\n  File ..."
}
```

| Field | Type | Description |
|-------|------|-------------|
| `workflow_id` | string | The workflow execution ID (matches checkpoint files) |
| `source` | string | Where the error originated (see table above) |
| `error_type` | string | Exception class name or error category |
| `error_message` | string | Human-readable error description |
| `timestamp` | string | ISO-8601 UTC timestamp |
| `context` | object | Varies by source -- includes phase, cost, task_id, target_file, etc. |
| `traceback` | string | Python traceback (only present when an exception was caught) |

The `context` object varies by error source:

- **Phase errors** include `phase`, `cost`, `duration_seconds`, `attempt`
- **Generation errors** include `task_id`, `target_file`
- **Workflow result errors** include `failed_steps`, `total_steps`, `metrics`


## Structured Log File

The SDK writes JSON-formatted logs to `~/.startd8/logs/startd8.log`. This is a broader stream than the task error store -- it includes INFO, WARNING, DEBUG messages too.

Error-relevant fields in log entries:

```json
{
  "timestamp": "2026-02-12T14:30:22.456Z",
  "level": "ERROR",
  "logger": "startd8.contractors.artisan_contractor",
  "message": "Phase implement failed after 3 attempt(s): ...",
  "exception": "Traceback (most recent call last):\n  ...",
  "exception_type": "PhaseExecutionError",
  "trace_id": "abc123...",
  "correlation_id": "req-456..."
}
```

### Useful log queries

```bash
# Errors in the last 24 hours
cat ~/.startd8/logs/startd8.log | jq 'select(.level == "ERROR")'

# Errors from a specific module
cat ~/.startd8/logs/startd8.log | jq 'select(.level == "ERROR" and (.logger | test("artisan")))'

# Cost warnings (budget approaching limit)
cat ~/.startd8/logs/startd8.log | jq 'select(.message | test("budget"; "i"))'
```

If you have the Loki stack running (see the [Loki Setup Guide](LOKI_SETUP_GUIDE.md)), these logs are automatically shipped and queryable via Grafana.

### OpenTelemetry shutdown note

During process exit, StartD8 runs a best-effort telemetry flush via `shutdown_otel()` so buffered spans/metrics/logs are not lost. The helper now flushes tracked providers without explicitly calling provider-level `shutdown()` again, which avoids duplicate-shutdown runtime noise (for example, `shutdown can only be called once`) when OpenTelemetry internals already handle final shutdown.

If you still see that message in older runs, treat it as teardown noise rather than a task-error-store failure. It should not create entries under `.startd8/task_errors/` unless a real workflow/phase exception occurred.


## Checkpoint Files

Checkpoint files at `.startd8/checkpoints/{workflow_id}.checkpoint.json` contain a snapshot of the workflow state at each phase boundary. They are primarily for resume, but they also contain error information:

```bash
# See which phase failed and why
jq '.phase_results[] | select(.status == "failed") | {phase, error_message, cost, duration_seconds}' \
  .startd8/checkpoints/artisan-PI-001.checkpoint.json

# See overall workflow status and cost at failure
jq '{status, cumulative_cost, last_completed_phase, timestamp}' \
  .startd8/checkpoints/artisan-PI-001.checkpoint.json
```

For feature-serial workflows, checkpoints also include per-feature partial results:

```bash
# See which features completed and which failed
jq '{completed_features, current_feature, current_feature_phase, feature_partial_results}' \
  .startd8/checkpoints/artisan-PI-001.checkpoint.json
```


## Grafana / Loki Integration

If you run the Loki observability stack (`docker-compose -f docker-compose.loki-stack.yml up -d`), the SDK's structured log entries are shipped to Loki via Promtail.

### Useful LogQL queries in Grafana

```logql
# All ERROR-level log entries from startd8
{job="startd8"} | json | level = "ERROR"

# Phase failures with cost
{job="startd8"} | json | level = "ERROR" | message =~ "Phase .* failed"

# Budget warnings
{job="startd8"} | json | message =~ "budget"

# Errors correlated to a specific trace
{job="startd8"} | json | trace_id = "abc123..."
```

See the [Loki Setup Guide](LOKI_SETUP_GUIDE.md) for full stack setup instructions.


## Programmatic Access

The `TaskErrorStore` class is a public API you can use in scripts or downstream tools.

### Reading errors

```python
from startd8.storage.error_store import TaskErrorStore

store = TaskErrorStore(project_root="/path/to/project")

# List all errors (newest first)
errors = store.list_errors()
for err in errors:
    print(f"[{err['timestamp']}] {err['source']}: {err['error_message']}")

# Filter to a specific workflow
errors = store.list_errors(workflow_id="artisan-PI-001", limit=10)

# Clear errors after investigation
store.clear(workflow_id="artisan-PI-001")
```

### Recording custom errors

If you build custom phase handlers or workflows, you can record errors to the same store:

```python
store.record_error(
    workflow_id="my-custom-workflow",
    source="validation",
    error_message="Schema validation failed: missing 'name' field",
    context={"file": "config.yaml", "line": 12},
)

# Or with an exception (traceback is captured automatically)
try:
    risky_operation()
except Exception as exc:
    store.record_error(
        workflow_id="my-custom-workflow",
        source="transform",
        error_message=str(exc),
        exception=exc,
    )
```

### Convenience wrappers

```python
# Phase failure with cost/duration context
store.record_phase_error(
    workflow_id="artisan-PI-001",
    phase="implement",
    error_message="LLM returned empty output",
    cost=0.42,
    duration_seconds=12.5,
)

# Code generation failure with task context
store.record_generation_error(
    workflow_id="artisan-PI-001",
    task_id="PI-003",
    error_message="Truncated response detected",
    target_file="src/mylib/auth.py",
)
```


## Recipes

### Recipe 1: Post-run error summary script

Save as `scripts/error_summary.sh`:

```bash
#!/usr/bin/env bash
# Print a summary of errors from the most recent workflow run
set -euo pipefail

ERRORS_DIR=".startd8/task_errors"

if [ ! -f "$ERRORS_DIR/errors.jsonl" ]; then
    echo "No errors recorded."
    exit 0
fi

TOTAL=$(wc -l < "$ERRORS_DIR/errors.jsonl" | tr -d ' ')
echo "=== Error Summary ($TOTAL total) ==="
echo ""

echo "By source:"
jq -r '.source' "$ERRORS_DIR/errors.jsonl" | sort | uniq -c | sort -rn
echo ""

echo "By error type:"
jq -r '.error_type' "$ERRORS_DIR/errors.jsonl" | sort | uniq -c | sort -rn
echo ""

echo "Most recent 5 errors:"
tail -5 "$ERRORS_DIR/errors.jsonl" | jq -r '"\(.timestamp | .[0:19]) [\(.source)] \(.error_message | .[0:80])"'
```

### Recipe 2: Clean up after a successful re-run

```bash
# After a successful workflow run, clear the error store
python3 -c "
from startd8.storage.error_store import TaskErrorStore
store = TaskErrorStore(project_root='.')
removed = store.clear()
print(f'Cleared {removed} error file(s)')
"
```

### Recipe 3: CI/CD error check

```bash
# Fail the CI pipeline if any errors were recorded during the run
if [ -f .startd8/task_errors/errors.jsonl ]; then
    ERROR_COUNT=$(wc -l < .startd8/task_errors/errors.jsonl | tr -d ' ')
    if [ "$ERROR_COUNT" -gt 0 ]; then
        echo "::error::$ERROR_COUNT workflow error(s) recorded"
        cat .startd8/task_errors/errors.jsonl | jq -r '"  - [\(.source)] \(.error_message)"'
        exit 1
    fi
fi
```

### Recipe 4: Python error digest for AI agents

```python
from startd8.storage.error_store import TaskErrorStore

store = TaskErrorStore(project_root=".")
errors = store.list_errors(limit=20)

if not errors:
    print("No errors found.")
else:
    for e in errors:
        ctx = e.get("context", {})
        parts = [
            f"[{e['source']}]",
            e["error_message"][:120],
        ]
        if "task_id" in ctx:
            parts.append(f"(task: {ctx['task_id']})")
        if "phase" in ctx and "cost" in ctx:
            parts.append(f"(cost: ${ctx['cost']:.4f})")
        print(" ".join(parts))
```
