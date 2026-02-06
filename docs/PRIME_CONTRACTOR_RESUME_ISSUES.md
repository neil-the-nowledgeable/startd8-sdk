# Prime Contractor Resume & Retry Issues

**Date:** 2026-02-06
**Discovered in:** contextcore-demo-retail persona onboarding workflow
**SDK version:** Post-`ebc9e66` (includes token config, workspace cleanup, AST accumulation detection)

## Context

Running `PrimeContractorWorkflow` across multiple sessions against
`contextcore-demo-retail` exposed issues with resume, retry, and state
management. The token/truncation/cleanup fixes from `ebc9e66` are working.
The remaining issues are about workflow state lifecycle.

---

## Issue 1: `FeatureQueue.add_feature()` Unconditionally Overwrites Loaded State

**Severity:** High
**File:** `src/startd8/contractors/queue.py:115-139`

### Problem

`add_feature()` does `self.features[feature_id] = spec` (line 132) with no
check for existing state. When a workflow script calls `add_feature()` for
features that were already loaded from `.prime_contractor_state.json`, the
loaded status (complete, failed, blocked) is silently replaced with a fresh
pending `FeatureSpec`.

This means any workflow script that declares its feature queue in code
(the expected pattern) will destroy persisted state on every invocation.

### Reproduction

```python
workflow = PrimeContractorWorkflow(project_root=root)
# Queue loads state from .prime_contractor_state.json:
#   P1_F1: complete, P1_F2: complete, P1_F3: failed

# This SHOULD be a no-op for completed features, but overwrites them:
workflow.queue.add_feature("P1_F1", "Feature 1", target_files=["a.py"])  # complete → pending
workflow.queue.add_feature("P1_F2", "Feature 2", target_files=["b.py"])  # complete → pending
workflow.queue.add_feature("P1_F3", "Feature 3", target_files=["c.py"])  # failed → pending

workflow.run()  # Re-runs ALL features from scratch
```

### Impact

- **Resume is broken.** Re-running a workflow script after partial completion
  re-processes every feature, not just the remaining ones.
- **`reset_failed_features()` is unreachable.** Calling it before
  `add_feature()` is useless (state will be overwritten). Calling it after
  works, but only by accident — the caller must know the ordering constraint.
- **`--reset-state` appears to be the only working mode.** In practice, every
  run starts from scratch, which is why `contextcore-demo-retail` only used
  `--reset-state`.

### Proposed Fix

`add_feature()` should preserve existing features that have progressed beyond
pending:

```python
def add_feature(self, feature_id, name, description="", dependencies=None, target_files=None):
    existing = self.features.get(feature_id)
    if existing and existing.status != FeatureStatus.PENDING:
        # Preserve completed/failed/blocked state from loaded JSON.
        # Update metadata (description, deps, targets) in case they changed.
        existing.name = name
        existing.description = description
        existing.dependencies = dependencies or []
        existing.target_files = target_files or []
        if feature_id not in self.order:
            self.order.append(feature_id)
        if self.auto_save:
            self.save_state()
        return existing

    # New feature or existing pending feature — create fresh spec
    spec = FeatureSpec(
        id=feature_id,
        name=name,
        description=description,
        dependencies=dependencies or [],
        target_files=target_files or [],
    )
    self.features[feature_id] = spec
    if feature_id not in self.order:
        self.order.append(feature_id)
    if self.auto_save:
        self.save_state()
    return spec
```

### Downstream Workaround

`contextcore-demo-retail` works around this by calling `retry_failed_features()`
**after** `add_feature()` on the live queue object, so the reset happens after
the overwrite. This is fragile and depends on understanding the bug.

---

## Issue 2: `workflow.run()` Not Wired to CLI in Downstream Scripts

**Severity:** Medium (documentation/example gap)

### Problem

The SDK provides `run(stop_on_failure=False)` to continue processing
independent features after a failure, and `reset_failed_features()` to retry
failed work. But the downstream workflow scripts (`contextcore-demo-retail`,
`ContextCore`, `wayfinder`) don't expose these as CLI flags.

The typical downstream `main()` looks like:

```python
workflow = build_workflow(...)
enqueue_features(workflow)
result = workflow.run()  # stop_on_failure defaults to True
```

When a feature fails for a transient reason (network timeout, API rate limit),
the entire workflow stops. The user must manually patch the state JSON or
restart from scratch.

### Proposed Fix

Add a reference implementation of CLI flags to the SDK documentation or
provide a `run_workflow()` helper that wires common flags:

```python
# In SDK: startd8.contractors.cli_helpers (or documented pattern)
def add_workflow_args(parser: argparse.ArgumentParser):
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reset-state", action="store_true",
        help="Delete state file and start fresh")
    parser.add_argument("--retry-failed", action="store_true",
        help="Reset failed/blocked features and resume")
    parser.add_argument("--stop-on-failure", action="store_true", default=True,
        help="Stop on first failure (default)")
    parser.add_argument("--continue-on-failure", action="store_true",
        help="Skip failed features and continue with independent ones")
    parser.add_argument("--clean", action="store_true",
        help="Clean workspace artifacts before running")
```

### Downstream Workaround

`contextcore-demo-retail` implements `--retry-failed` manually with a
`retry_failed_features()` function that operates on the workflow's queue
after `enqueue_features()` runs (to work around Issue 1).

---

## Issue 3: `--reset-state` Doesn't Clean Generated Artifacts

**Severity:** Medium
**Note:** `clean_workspace()` exists but isn't wired into the reset path.

### Problem

The common downstream pattern for `--reset-state` is:

```python
if args.reset_state:
    state_file = project_root / ".prime_contractor_state.json"
    if state_file.exists():
        state_file.unlink()
```

This only deletes the queue state. The `generated/` staging directory, target
files with accumulated AST-merge layers, `.backup` files, and `__pycache__`
all persist. On re-run, `ASTMergeStrategy` concatenates new LLM output on top
of existing bloated files.

The SDK's `clean_workspace()` method (added in `ebc9e66`) fixes this, but:
1. It's not called automatically by `--reset-state`
2. Downstream scripts don't know about it (they predate `ebc9e66`)

### Proposed Fix

Either:
- Document that `clean_workspace()` should be called alongside state reset
- Or wire `clean_workspace(include_targets=True)` into a `full_reset()` method

---

## Issue 4: Downstream Script Uses Workarounds for Already-Fixed SDK Issues

**Severity:** Low (tech debt, not a bug)

### Problem

`contextcore-demo-retail/personas/run_prime_contractor.py` contains:

1. **`SafeCodeGenerator` subclass** (100+ lines) — monkey-patches
   `resolve_agent_spec` to inject `max_tokens` and adds truncation config
   to the workflow. The SDK's `LeadContractorCodeGenerator` now natively
   supports `max_tokens` and `fail_on_truncation` (since `ebc9e66`).

2. **`clean_workspace.py`** (130+ lines) — external script that deletes
   `generated/`, `.backup`, `__pycache__`, and target files. The SDK's
   `PrimeContractorWorkflow.clean_workspace()` does the same thing.

3. **Post-construction attribute overrides** — `wf.max_lines_per_feature = 300`.
   The SDK now accepts these as constructor params.

### Proposed Fix

Update the downstream script to use native SDK features:

```python
# Before (workaround):
code_generator=SafeCodeGenerator(
    max_tokens=32768,
    fail_on_truncation=False,
    lead_agent="anthropic:claude-sonnet-4-20250514",
    drafter_agent="gemini:gemini-2.5-flash-lite",
)

# After (native):
code_generator=LeadContractorCodeGenerator(
    lead_agent="anthropic:claude-sonnet-4-20250514",
    drafter_agent="gemini:gemini-2.5-flash-lite",
    max_tokens=32768,
    fail_on_truncation=False,
)
```

```python
# Before (workaround):
wf = PrimeContractorWorkflow(...)
wf.max_lines_per_feature = 300
wf.max_tokens_per_feature = 1000

# After (native):
wf = PrimeContractorWorkflow(
    ...,
    max_lines_per_feature=300,
    max_tokens_per_feature=1000,
)
```

---

## Summary

| # | Issue | Severity | SDK Status |
|---|-------|----------|------------|
| 1 | `add_feature()` overwrites loaded state | High | **FIXED** — preserves non-pending features |
| 2 | CLI flags not wired / no reference implementation | Medium | **FIXED** — `add_workflow_args()` / `apply_workflow_args()` |
| 3 | `--reset-state` doesn't call `clean_workspace()` | Medium | **FIXED** — `full_reset()` method |
| 4 | Downstream uses stale workarounds | Low | SDK already fixed; downstream needs update |

## Migration Guide

### Issue 1 — Resume now works automatically

`FeatureQueue.add_feature()` now preserves features that have progressed beyond
pending.  Scripts that declare their full queue on every invocation will automatically
skip completed features on re-run.  No code changes needed in downstream scripts.

### Issue 2 — CLI helpers

```python
import argparse
from startd8.contractors import (
    PrimeContractorWorkflow,
    add_workflow_args,
    apply_workflow_args,
)

parser = argparse.ArgumentParser()
add_workflow_args(parser)          # adds --dry-run, --reset-state, --retry-failed, etc.
args = parser.parse_args()

workflow = PrimeContractorWorkflow(project_root=root, dry_run=args.dry_run)
# ... add features ...
apply_workflow_args(workflow, args)  # applies flags in correct order
result = workflow.run(stop_on_failure=not args.continue_on_failure)
```

### Issue 3 — Full reset

Replace manual state file deletion with:

```python
# Before:
state_file = project_root / ".prime_contractor_state.json"
if state_file.exists():
    state_file.unlink()

# After:
workflow.full_reset()              # deletes state + cleans generated/, .backup, __pycache__
workflow.full_reset(include_targets=True)  # also removes target files
```

## Appendix: Session Timeline

This investigation ran across a single troubleshooting session against
`contextcore-demo-retail`'s persona onboarding workflow:

1. **Initial failure:** P1-F5 (Core lib tests) truncated at 14,435 output
   tokens against a 16,384 limit. Root cause: accumulated AST-merge layers
   across re-runs inflated source files (loader.py: 1,078 lines), making
   tests too large to generate.

2. **Fixes applied:**
   - Split P1-F5 into P1-F5a (loader tests) + P1-F5b (relevance tests)
   - Created `SafeCodeGenerator` with `max_tokens=32768` and
     `fail_on_truncation=False`
   - Created `clean_workspace.py` to remove accumulated artifacts
   - Raised `max_lines_per_feature` to 300

3. **Second run (clean workspace):** 8/9 features succeeded. P2-F3
   (Collaboration outputs) failed due to Anthropic API network timeout.

4. **Retry attempt:** `--retry-failed` flag triggered a from-scratch re-run
   instead of retrying just P2-F3. Root cause: `add_feature()` overwrites
   loaded state (Issue 1). Fixed by calling `reset_failed_features()` after
   `add_feature()` on the live queue object.

5. **Discovery:** The SDK (post-`ebc9e66`) already supports `max_tokens`,
   `fail_on_truncation`, `clean_workspace()`, `reset_failed_features()`,
   and `run(stop_on_failure=False)`. The downstream script predates these
   fixes and uses manual workarounds instead.
