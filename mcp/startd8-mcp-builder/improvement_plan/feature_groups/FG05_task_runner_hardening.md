# FG05 — Task Runner Hardening (Safety, Determinism, Validation)

## Goal

Strengthen `tasks.list`, `tasks.status`, and `tasks.run` to be:

- safe by default (path + extension policy)
- predictable (strict response contract, deterministic execution order)
- easier to debug (diffs + validation)

---

## Current pain points

- `ALLOW_AUTO_DEPS` is defined but not enforced.
- Security policy defaults are permissive in some environments.
- `tasks.run` mixes multiple responsibilities (select task, plan deps, prompt LLM, parse, validate, diff, apply).

---

## Design: enforce ALLOW_AUTO_DEPS

If `params.auto=true` but `ALLOW_AUTO_DEPS=false`, return `failed_precondition`.

**Example error:**

```json
{
  "error": "failed_precondition",
  "message": "auto dependency resolution is disabled",
  "data": {"auto": true, "allow_auto_deps": false}
}
```

---

## Design: safe file-write policy

### Policy knobs

- `ALLOWED_EXTENSIONS` (allowlist) should default to a safe set for this project, e.g.
  - `md,txt,py,json,yaml,yml,toml,ini,xml,ts,tsx,js,jsx,css,html`
- `BLOCKED_EXTENSIONS` remains as defense-in-depth

### Behavior

- validate every action path under `PROJECT_ROOT`
- reject on first invalid action with `invalid_params`

---

## Design: add `tasks.validate`

A new read-only tool that:

- parses the task list
- validates:
  - unknown dependencies
  - dependency cycles
  - blocked tasks
  - runnable count
- returns summary + diagnostics

**Example response:**

```json
{
  "data": {
    "file": ".../MASTER_TASK_LIST.md",
    "counts": {"total": 10, "completed": 3, "runnable": 2},
    "issues": [
      {"type": "unknown_dependency", "task": "TASK-999", "dep": "TASK-404"},
      {"type": "cycle", "chain": ["TASK-001", "TASK-002", "TASK-001"]}
    ]
  }
}
```

---

## Design: internal refactor (keep behavior)

Split `tasks.run` into:

- `select_task(tasks, id)`
- `build_execution_plan(task, auto, caps)`
- `generate_actions(agent, prompt)`
- `validate_actions(actions)`
- `compute_diffs(actions)`
- `apply_actions(actions)`

This makes it easier to test each stage and reduces risk.

---

## Tests

Add/extend tests covering:

- `ALLOW_AUTO_DEPS` enforcement
- default extension allowlist behavior
- `tasks.validate` output
- malicious traversal attempts

---

## Worktree boundaries

Expected files changed (post-FG01 module split):

- `startd8_mcp_server/tasks/runner.py`
- `startd8_mcp_server/tasks/validation.py`
- tests under `tests/test_tasks_*.py`

---

## Acceptance criteria

- `ALLOW_AUTO_DEPS` is enforced.
- Unsafe file extensions are blocked by default.
- A `tasks.validate` tool exists and is covered by tests.
- All task tools emit canonical response envelopes (FG02).
