# FG06 — Observability and DevEx (Diagnostics, CI, Packaging)

## Goal

Make the server easier to operate and contribute to:

- consistent, low-noise logs
- fast diagnosis when Cursor runs a different env than your shell
- basic CI so regressions are caught early
- packaging/entrypoints for predictable startup

---

## Observability

### Request correlation IDs

Add a simple request ID per tool call and include it in:

- debug logs
- response envelope `meta.request_id`

**Example (illustrative):**

```python
import uuid

def new_request_id() -> str:
    return uuid.uuid4().hex[:12]
```

### Debug logging toggle

- `MCP_DEBUG=1` enables `[mcp-debug]` logs
- default: minimal logging

### Structured log option

Optional `MCP_LOG_JSON=1` writes one JSON object per line for easy parsing.

---

## “It started but calls aren’t hitting this process” diagnostics

Codify the workflow described in `MCP_SKILL_ISSUE_SUMMARY.md`:

- add a `startd8_diagnostics` tool (see FG04)
- update docs to require Cursor config uses `/bin/sh -lc` and the canonical launcher

---

## CI (GitHub)

### Minimal GitHub Actions workflow

- run `pytest` on Python 3.11–3.13
- cache pip/uv

**Example workflow (illustrative):**

```yaml
name: tests
on: [push, pull_request]
jobs:
  pytest:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python: ["3.11", "3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python }}
      - run: pip install -r requirements-server.txt -r requirements-dev.txt
      - run: pytest -q
```

### Linting baseline

Add `ruff` (fast) and enforce basic rules:

- unused imports
- obvious bugs

---

## Packaging / entrypoints

### Why

Cursor configs are more reliable when they call a stable entrypoint rather than a local shell script with ad-hoc env.

### Plan

- keep `startd8_mcp.py` for backward compatibility
- add `python -m startd8_mcp_server` entrypoint (FG01)
- later: publish as a package (optional) or use editable install

---

## Docs cleanup

Update docs to:

- remove hard-coded absolute paths where possible
- provide a single “canonical” Cursor config snippet
- document env vars in one place

---

## Worktree boundaries

Expected files changed:

- `startd8_mcp_server/logging_utils.py`
- `README_SERVER.md`, `QUICKSTART.md`, `cursor-mcp-config.json`
- `.github/workflows/tests.yml` (once git repo exists)

---

## Acceptance criteria

- A request ID appears in responses and logs.
- Debug logging is controllable via env.
- A basic CI workflow exists and passes.
- Docs provide one canonical startup path that avoids PYTHONPATH drift.
