# TODO Completion v3 — Prime Contractor Integration Plan

**Requirements:** `docs/design/prime/TODO_COMPLETION_WORKFLOW_REQUIREMENTS.md` v3.0.0
**Created:** 2026-03-21
**Estimated scope:** ~150 lines changed across 3 files + ~100 lines tests

---

## Context

The v2 TODO completion workflow ran as a separate `TodoCompletionWorkflow` class that
instantiated a second `PrimeContractorWorkflow`. This produced a 0% completion rate
across all production runs (run-079: TypeError, run-084: LLM overwrite + first-failure
abort). The v3 design eliminates the separate workflow entirely by injecting TODO tasks
into the primary Prime Contractor queue and dispatching them through existing
infrastructure.

### Existing infrastructure reused

- `_try_copy_shortcut()` pattern → model for `_try_uncomment_shortcut()`
- `_thread_supplemental_context()` → already injects `instrumentation_contract`
- `load_seed_context()` → already loads `instrumentation_hints` from onboarding
- `uncomment_block()` in `todo_scanner.py` → core deterministic function
- `TodoUncommentStep` in repair pipeline → remains as LLM-output repair fallback
- `add_features_from_seed()` → queue boundary for injecting TODO tasks
- Per-task error isolation in `develop_feature()` → inherited automatically

---

## Step 1: Thread `task_type` through queue boundary

**File:** `src/startd8/contractors/queue.py`
**Requirement:** REQ-TCW-201

In `add_features_from_seed()`, after the existing metadata threading block (line ~299-321),
add `task_type` preservation:

```python
# REQ-TCW-201: Preserve task_type for dispatch in develop_feature()
task_type = task.get("task_type")
if task_type:
    meta["task_type"] = task_type
    # For uncomment tasks, preserve full context needed by shortcut
    todo_context = context.get("todo_line") or context.get("comment_block")
    if todo_context:
        meta["_todo_context"] = context
```

**What this does:** When the queue ingests a seed task with `task_type: "uncomment"`,
the type and its context survive into `FeatureSpec.metadata`. The `develop_feature()`
dispatch can then read `feature.metadata.get("task_type")` to select the shortcut.

**Test:** Add a unit test to `tests/unit/contractors/test_queue.py` that verifies
`task_type` and `_todo_context` survive the queue boundary.

**Lines changed:** ~8 in queue.py, ~20 in test file

---

## Step 2: Add `_try_uncomment_shortcut()` to Prime Contractor

**File:** `src/startd8/contractors/prime_contractor.py`
**Requirement:** REQ-TCW-300

Add the method following the exact pattern of `_try_copy_shortcut()` (line 3314):

```python
def _try_uncomment_shortcut(self, feature: FeatureSpec) -> Optional[bool]:
    """Phase 0.5: Deterministic uncomment for Category A TODO tasks.

    Returns True (success), False (failure), or None (not an uncomment task).
    """
    if feature.metadata.get("task_type") != "uncomment":
        return None

    from startd8.validators.todo_scanner import uncomment_block, _detect_language

    target_files = feature.target_files or []
    if not target_files:
        logger.warning("Uncomment task '%s' has no target files", feature.name)
        self.queue.fail_feature(feature.id, "No target files for uncomment")
        return False

    try:
        for tf in target_files:
            file_path = Path(tf)
            if not file_path.is_absolute():
                file_path = self.project_root / tf
            if not file_path.is_file():
                logger.warning("Uncomment target not found: %s", file_path)
                continue

            content = file_path.read_text(encoding="utf-8", errors="replace")
            language = _detect_language(str(file_path))
            result, count = uncomment_block(content, language=language)
            if count > 0:
                file_path.write_text(result, encoding="utf-8")
                logger.info(
                    "Uncommented %d block(s) in %s (cost=$0.00)",
                    count, file_path,
                )

        feature.generated_files = [str(f) for f in target_files]
        feature.status = FeatureStatus.GENERATED
        self._save_queue_state_with_mode()
        return True

    except (OSError, ValueError) as exc:
        logger.error("Uncomment failed for '%s': %s", feature.name, exc)
        self.queue.fail_feature(feature.id, f"Uncomment failed: {exc}")
        return False
```

Then wire it into `develop_feature()` between Phase 0 and Phase 1:

```python
# Phase 0: Copy shortcut
copy_result = self._try_copy_shortcut(feature)
if copy_result is not None:
    return copy_result

# Phase 0.5: Uncomment shortcut (REQ-TCW-300)
uncomment_result = self._try_uncomment_shortcut(feature)
if uncomment_result is not None:
    return uncomment_result
```

**What this does:** Category A TODO tasks (`task_type: "uncomment"`) hit this shortcut
before preflight, context assembly, or LLM generation. They're resolved deterministically
at $0.00 cost. All other tasks pass through to Phase 1+ unchanged.

**Test:** Add tests to `tests/unit/contractors/test_prime_contractor.py`:
- Uncomment task with valid target file → returns True, file modified
- Uncomment task with missing target → returns False, feature failed
- Non-uncomment task → returns None (passes through)

**Lines changed:** ~35 in prime_contractor.py, ~2 wiring lines, ~40 in test file

---

## Step 3: Add post-generation TODO scan trigger

**File:** `src/startd8/contractors/prime_contractor.py`
**Requirement:** REQ-TCW-203

In `run()`, after the primary task queue completes and before postmortem, add:

```python
# REQ-TCW-203: Post-generation TODO scan + task injection
if self._enable_todo_completion and not self.dry_run:
    self._run_todo_scan_and_inject()
```

The method:

```python
def _run_todo_scan_and_inject(self) -> None:
    """Scan generated output for TODOs, derive tasks, inject into queue."""
    generated_dir = self._resolve_generated_dir()
    if not generated_dir or not generated_dir.is_dir():
        return

    try:
        from startd8.validators.todo_scanner import scan_directory
        from startd8.seeds.todo_derivation import derive_tasks_from_todos

        inventory = scan_directory(
            str(generated_dir),
            instrumentation_contract=self._instrumentation_contract,
        )

        # Filter to A and B only
        inventory.entries = [
            e for e in inventory.entries if e.category in {"A", "B"}
        ]
        inventory.compute_summary()

        if not inventory.entries:
            logger.info("TODO scan: no actionable TODOs found in %s", generated_dir)
            return

        logger.info(
            "TODO scan: %d entries (A=%d, B=%d)",
            inventory.summary.get("total", 0),
            inventory.summary.get("A", 0),
            inventory.summary.get("B", 0),
        )

        # Persist inventory
        instr_dir = Path(self._output_dir) / "instrumentation"
        instr_dir.mkdir(parents=True, exist_ok=True)
        inventory.save(instr_dir / "todo-inventory.json")

        tasks = derive_tasks_from_todos(
            inventory,
            instrumentation_contract=self._instrumentation_contract,
            source_run_id=getattr(self, '_run_id', ''),
        )

        if not tasks:
            return

        # Enforce max limit
        max_todo_tasks = 20
        if len(tasks) > max_todo_tasks:
            logger.warning(
                "TODO scan produced %d tasks, limiting to %d",
                len(tasks), max_todo_tasks,
            )
            tasks = tasks[:max_todo_tasks]

        # Write as seed and inject into queue
        import json
        seed = {"schema_version": "1.0.0", "source": "todo-scan", "tasks": tasks}
        seed_path = instr_dir / "instrumentation-seed.json"
        seed_path.write_text(json.dumps(seed, indent=2, default=str), encoding="utf-8")

        added = self.queue.add_features_from_seed(str(seed_path))
        logger.info("Injected %d TODO tasks into queue", len(added))

        # Process the injected tasks
        for feature_id in [f.id for f in added]:
            feature = self.queue.get_next_feature()
            if feature is None:
                break
            self.develop_feature(feature)

    except Exception as exc:
        logger.warning("TODO scan failed (non-fatal): %s", exc, exc_info=True)
```

Add the config flag:

```python
# In __init__():
self._enable_todo_completion = kwargs.get("enable_todo_completion", False)
```

**What this does:** After all structural tasks complete, the workflow scans `generated/`
for TODOs, derives tasks, injects them into the same queue, and processes them through
the same `develop_feature()` loop. Category A hits the shortcut; Category B goes through
normal LLM generation with instrumentation contract already in context.

**Test:** Integration test in `tests/unit/contractors/test_todo_integration.py`:
- Mock `scan_directory` returning 2 entries (1 A, 1 B) → verify both processed
- Mock `scan_directory` returning empty → verify no tasks injected
- Verify `enable_todo_completion=False` skips scan entirely

**Lines changed:** ~60 in prime_contractor.py, ~5 init wiring, ~50 in test file

---

## Step 4: Update `todo_derivation.py` — remove separate seed file write

**File:** `src/startd8/seeds/todo_derivation.py`
**Requirement:** REQ-TCW-200

The function already returns a task list. Remove any references to writing a separate
seed file (that's now handled by the caller in Step 3). Verify the returned task dicts
include all fields needed by `add_features_from_seed()`:

Required fields per task:
- `task_id` (e.g., `TODO-001`) ✓ already set
- `title` ✓ already set
- `task_type` (`uncomment` | `implement` | `edit`) ✓ already set
- `config.task_description` ✓ already set
- `config.context.target_files` ✓ already set
- `target_files` ✓ already set
- `depends_on` ✓ already set
- `mode: "edit"` ✓ already set

No changes needed to `derive_tasks_from_todos()` itself — the task format is already
compatible with `add_features_from_seed()`.

**Lines changed:** 0 (verify only)

---

## Step 5: Delete the separate workflow

**Files to delete or gut:**
- `src/startd8/workflows/builtin/todo_completion_workflow.py` — delete `_execute_plan()` method and `run()` method body. Keep the class shell with a deprecation note pointing to the `--todo-completion` flag, or delete entirely.
- `scripts/run_todo_completion.py` — deprecate with a message pointing to `--todo-completion` on the main pipeline.

**Do NOT delete yet if there are imports or entry points referencing these.** First check:
```bash
grep -rn 'TodoCompletionWorkflow\|todo_completion_workflow\|run_todo_completion' src/ scripts/ tests/
```

If references exist only in tests, update tests to use the new integration path.

**Lines deleted:** ~500 (workflow class + script)

---

## Step 6: Tests

### New tests

| Test file | Tests | Purpose |
|-----------|-------|---------|
| `tests/unit/contractors/test_queue_task_type.py` | 3 | `task_type` threading through queue |
| `tests/unit/contractors/test_uncomment_shortcut.py` | 4 | `_try_uncomment_shortcut()` dispatch |
| `tests/unit/contractors/test_todo_integration.py` | 3 | End-to-end scan→inject→execute flow |

### Existing tests to update

| Test file | Change |
|-----------|--------|
| `tests/unit/workflows/test_todo_completion_workflow.py` | Update or delete — workflow class is deprecated |
| `tests/unit/validators/test_todo_scanner.py` | No changes — scanner is unchanged |
| `tests/unit/validators/test_instrumentation_coverage.py` | No changes |

---

## Execution Order

| Step | Requirement | Risk | Dependency |
|------|------------|------|------------|
| 1. Queue metadata | REQ-TCW-201 | Low | None |
| 2. Uncomment shortcut | REQ-TCW-300 | Low | Step 1 |
| 3. Post-gen scan trigger | REQ-TCW-203 | Medium | Steps 1+2 |
| 4. Verify todo_derivation | REQ-TCW-200 | Low | None (parallel with 1-2) |
| 5. Delete separate workflow | — | Low | Steps 1-3 passing |
| 6. Tests | — | Low | Steps 1-3 |

Steps 1 and 4 can run in parallel. Steps 2 and 3 are sequential (3 depends on 2).
Step 5 runs last after all tests pass.

---

## Validation

After implementation, re-run the online-boutique pipeline with `ENABLE_TODO_COMPLETION=true`
and verify:

1. **Category A uncomment tasks:** $0.00 cost, target files modified, `status: completed`
2. **Category B implement tasks:** Routed through complexity router, instrumentation contract in gen_context, LLM produces implementation
3. **Per-task isolation:** A failed TODO-003 does not block TODO-004
4. **Kaizen metrics:** `todo_completion_rate` > 0% (the bar is low — anything above v2's 0%)
5. **No API errors:** No `TypeError`, no `unexpected keyword argument`

Expected outcome for a typical online-boutique run with 4 TODOs (2A + 2B):
- TODO-001, TODO-002 (uncomment): $0.00, ~0.1s each
- TODO-003, TODO-004 (implement): ~$0.12 each via Sonnet/Haiku
- Total instrumentation cost: ~$0.25
- Completion rate: ≥50% (up from 0%)
