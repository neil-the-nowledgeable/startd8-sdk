# Task Runner Hardening Plan

Design details and examples for the next iteration of the MCP task runner, based on the latest implementation and test work.

## 1) Response normalization (JSON everywhere)

- Return structured JSON on all paths, including early validation errors.
- Shape: `{"error": "<code>|null", "message": "<string>", "data": {...}}` plus success fields.
- Sample error for blocked task:

```json
{
  "error": "failed_precondition",
  "message": "Task TASK-010 is blocked",
  "data": {
    "task": "TASK-010",
    "status": "🚫"
  }
}
```

- Sample success (dry-run with diffs):

```json
{
  "dry_run": true,
  "file": "/abs/path/MASTER_TASK_LIST.md",
  "execution_order": ["TASK-001"],
  "results": [
    {
      "task": { "id": "TASK-001", "priority": "🟡", "status": "🔓" },
      "files": ["proj/file.txt"],
      "diffs": [
        { "path": "proj/file.txt", "diff": "@@ -0,0 +1,1 @@\n+hello" }
      ],
      "agent": { "name": "mock", "provider": "mock", "model": "mock-model" }
    }
  ],
  "modified_files": ["proj/file.txt"]
}
```

## 2) Path validation (prod vs tests)

- Keep production guard using `validate_task_file_path(action.path, PROJECT_ROOT)`.
- Allow configurable `allowed_extensions` / `blocked_extensions` (env/manifest).
- Tests can monkeypatch to a permissive resolver under tmp roots (already done).
- Add explicit 400-style error on path escape with `invalid_params`.

## 3) Expanded tests

- Add error-path coverage:
  - Blocked task.
  - Unknown dependency.
  - Cycle detection payload (`data.cycle`).
  - Auto-deps cap exceeded (depth/tasks).
  - Agent not allowed (allowlist).
  - Parser failure (bad XML) → `invalid_params`.
  - Apply failure path → `internal` with files list.
- Add status summary test for `tasks.status` including `runnable`.
- Add diff shape test with multiple files.

## 4) Pydantic cleanup

- Swap deprecated `min_items`/`max_items` → `min_length`/`max_length` in `CompareAgentsInput` (and any new inputs) to drop warnings.
- Leave SDK upstream warnings untouched for now; consider suppression in pytest if noisy.

## 5) Manifest alignment

- Ensure manifest advertises:
  - Capability flag `tasks:execute`.
  - Resources `task-list`, `task-log` with env defaults.
  - Commands: `tasks.list`, `tasks.status`, `tasks.run` with param defaults.
- Example manifest fragment:

```yaml
capabilities:
  - resources:read
  - resources:write
  - commands:execute
  - tasks:execute
resources:
  - name: task-list
    path: ${TASK_LIST_PATH:-MASTER_TASK_LIST.md}
    readOnly: false
  - name: task-log
    path: ${TASK_LOG_PATH:-logs/task-execution.log}
    readOnly: false
commands:
  - name: tasks.run
    params:
      - { name: id, type: string, required: false }
      - { name: file, type: string, required: false, default: ${TASK_LIST_PATH:-MASTER_TASK_LIST.md} }
      - { name: auto, type: boolean, required: false, default: false }
      - { name: agent, type: string, required: false, default: ${DEFAULT_AGENT:-claude} }
      - { name: dry_run, type: boolean, required: false, default: true }
```

## 6) Audit log defaults

- Keep JSONL with fields: timestamp, task_id, action, agent, dry_run/applied, files, result, error.
- Default on: `${PROJECT_ROOT}/logs/task-execution.log`; disable via `TASK_LOG_ENABLED=false`.
- Optional rotation: size cap or days via env/manifest.

## 7) Client-facing diffs

- Continue surfacing diffs in `tasks.run` dry-run/apply payloads.
- If later needed, add `tasks.diff` to render cached dry-run diffs without re-selection.

## 8) Auto-deps behavior (confirmed)

- Recursive execution when `auto=true`, gated by `ALLOW_AUTO_DEPS`.
- Caps: `AUTO_MAX_DEPTH` (default 5), `AUTO_MAX_TASKS` (default 20).
- Exceeding caps → `failed_precondition` with `data.order`.
- Cycle detection → `invalid_params` with `data.cycle`.

## 9) Agent allowlist

- Validate against `ALLOWED_AGENTS` + `DEFAULT_AGENT`.
- Reject others with `invalid_params` and `allowed_agents` list.
- Include agent metadata in responses.

## 10) Follow-up implementation checklist

- [ ] Normalize error responses in `tasks.run` to structured JSON.
- [ ] Add the expanded tests above.
- [ ] Update manifest file with tasks capability/resources/commands.
- [ ] Add env/manifest knobs for path extensions and audit log rotation (optional).
- [ ] Consider suppressing/cleaning pydantic warnings in tests.
