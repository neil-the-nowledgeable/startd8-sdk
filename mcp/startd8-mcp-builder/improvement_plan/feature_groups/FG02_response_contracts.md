# FG02 — Response Contracts (JSON-First Everywhere)

## Goal

Make every MCP tool return a **single canonical JSON envelope** on success and error, so evaluators/clients can consume outputs without special-casing strings vs JSON vs Markdown.

Markdown remains available as a **view**, but the JSON envelope is always the source of truth.

---

## Current pain points

- Some tools return raw Markdown strings.
- Some tools return raw JSON (not wrapped).
- Error paths frequently return plain strings.
- Downstream automation (evaluations/benchmarks) has to handle many shapes.

---

## Canonical envelope

### Envelope schema (v1)

```json
{
  "schema_version": 1,
  "ok": true,
  "error": null,
  "message": "optional human summary",
  "data": {},
  "meta": {
    "tool": "startd8_use_skill",
    "request_id": "...",
    "ts": "2025-12-12T00:00:00Z"
  },
  "view": {
    "format": "markdown",
    "content": "optional rendered view"
  }
}
```

### Error codes

- `invalid_params`
- `failed_precondition`
- `not_found`
- `unauthorized`
- `rate_limited`
- `internal`

---

## Implementation design

Create `startd8_mcp_server/responses.py`:

```python
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

SCHEMA_VERSION = 1


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def ok(*, tool: str, data: Optional[Dict[str, Any]] = None, message: Optional[str] = None,
       request_id: Optional[str] = None, view: Optional[Dict[str, Any]] = None) -> str:
    payload: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "error": None,
        "message": message,
        "data": data or {},
        "meta": {"tool": tool, "request_id": request_id, "ts": _now_iso()},
        "view": view,
    }
    return json.dumps(payload, indent=2)


def fail(*, tool: str, error: str, message: str, data: Optional[Dict[str, Any]] = None,
         request_id: Optional[str] = None, view: Optional[Dict[str, Any]] = None) -> str:
    payload: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "ok": False,
        "error": error,
        "message": message,
        "data": data or {},
        "meta": {"tool": tool, "request_id": request_id, "ts": _now_iso()},
        "view": view,
    }
    return json.dumps(payload, indent=2)
```

### Rendering rule

- If the caller requests Markdown (e.g. `response_format=markdown`), return the same envelope but include:

```json
"view": {"format": "markdown", "content": "..."}
```

- If the caller requests JSON-only, either omit `view` or set it to `null`.

---

## Tool-by-tool migration plan

Start with 3 representative tools (to prove the pattern):

1) `startd8_use_skill`
2) `tasks.run`
3) `startd8_list_skills`

Then apply to remaining tools.

---

## Tests

Add tests asserting:

- `json.loads(result)` succeeds for both success and error paths
- `schema_version == 1`
- `ok` boolean is correct
- `error` is either `null` or one of the allowed codes

---

## Worktree boundaries

- FG02 owns `responses.py` and updating tools to use it.
- Other feature groups should only call `ok()/fail()`.

---

## Acceptance criteria

- All tools return JSON envelopes (no plain-string errors).
- Markdown output is available as `view.content` (not as the top-level response).
- Tests updated/added to validate the contract.
