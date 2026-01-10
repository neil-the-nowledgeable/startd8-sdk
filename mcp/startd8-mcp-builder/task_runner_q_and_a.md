# Task Runner Q&A

## 1) Response schema
- **Answer:** Normalize to a single JSON envelope for all outcomes. For success, include `error: null`, `message` (optional), `execution_order`, `results`, and any task/file metadata. For errors, set `error` to a machine code (`invalid_params`, `failed_precondition`, `internal`, etc.), provide a human-readable `message`, and optional `data` (e.g., `cycle`, `order`, `files`). Versioning can be implicit via server version, but add a `schema_version` field (e.g., `1`) if clients need contract stability.

Example error:
```json
{
  "error": "failed_precondition",
  "message": "Task TASK-010 is blocked",
  "data": { "task": "TASK-010", "status": "🚫" }
}
```

Example success (dry-run):
```json
{
  "error": null,
  "message": "Dry-run complete",
  "dry_run": true,
  "execution_order": ["TASK-001"],
  "results": [
    {
      "task": { "id": "TASK-001", "priority": "🟡", "status": "🔓" },
      "files": ["proj/file.txt"],
      "diffs": [{ "path": "proj/file.txt", "diff": "@@ -0,0 +1,1 @@\n+hello" }],
      "agent": { "name": "mock", "provider": "mock", "model": "mock-model" }
    }
  ],
  "modified_files": ["proj/file.txt"],
  "schema_version": 1
}
```

## 2) Path validation
- **Answer:** Production defaults: allow all text/code extensions except a small blocked set (`.exe`, `.dll`, `.bat`, `.sh`, `.cmd`, `.com`); allowlist and blocklist tunable via env/manifest. Enforce under `PROJECT_ROOT` with traversal guard. Tests can explicitly monkeypatch to a permissive resolver, but defaults should mirror production unless a test opts out.

## 3) Manifest source
- **Answer:** Manifest should live in the repo (e.g., `cursor-mcp-config.json` or a `manifest.json` served by the MCP server) and be loaded at server start. Env defaults in the manifest are authoritative defaults; runtime env overrides still apply, but manifest values should be treated as the canonical documented defaults the server advertises to clients.

## 4) Audit logging
- **Answer:** Use JSONL, best-effort writes (logging failures should not fail the command). Default rotation: time-based (e.g., 7 or 14 days) plus optional size cap for extreme cases. Keep an env/manifest toggle `TASK_LOG_ENABLED=false` to disable. Include fields: timestamp, task_id, action, agent, dry_run/applied, files, result, error. 

