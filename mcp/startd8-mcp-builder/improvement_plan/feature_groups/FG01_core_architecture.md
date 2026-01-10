# FG01 — Core Architecture Refactor (Worktree-Safe)

## Goal

Make the MCP server **easier to change safely** by breaking up the current monolithic `startd8_mcp.py` into a small set of modules with clear boundaries, while preserving:

- tool names and behavior
- stdio transport
- the current tests (or adjusting them with minimal diff)

This feature group is intentionally **first** because it defines file layout that other worktrees will build on.

---

## Current pain points

- `startd8_mcp.py` contains multiple domains (skills, task runner, prompt framework tools, logging hacks).
- Cross-cutting edits cause merge conflicts.
- Small changes risk unintended side effects because utilities are all global.

---

## Proposed module layout (avoid import-name collision)

Because you already have a top-level `startd8_mcp.py` file, we should **not** create a package named `startd8_mcp/` in the same directory.

Instead:

- keep `startd8_mcp.py` as the stable entrypoint + public import surface
- move implementation into a package like `startd8_mcp_server/`

### Target tree

```
startd8-mcp-builder/
  startd8_mcp.py                  # thin shim: re-export tools + run server
  startd8_mcp_server/
    __init__.py                   # re-export tool callables/types
    app.py                        # FastMCP instance + registration
    config.py                     # env parsing + defaults
    responses.py                  # canonical response envelope helpers (FG02)
    logging_utils.py              # safe logging + debug helpers
    skills/
      discovery.py                # find/parse skills, caching (FG03)
      resources.py                # skill:// resource handlers
      execution.py                # provider selection + execution (FG04)
    tasks/
      runner.py                   # tasks.list/status/run (FG05)
      validation.py               # cycle/deps checks
    prompts/
      tools.py                    # prompt framework tools
```

---

## Migration strategy (no behavior change)

### Step 1: Create the package and move code without changing interfaces

- Create `startd8_mcp_server/app.py` with `mcp = FastMCP("startd8_mcp")`.
- Move existing tool functions into the appropriate modules.
- In `startd8_mcp_server/__init__.py`, re-export:
  - `mcp`
  - all tool callables
  - all Pydantic input models

### Step 2: Keep `startd8_mcp.py` as the shim

**Example shim (illustrative):**

```python
# startd8_mcp.py
from startd8_mcp_server import (
    mcp,
    # tool callables
    startd8_list_skills,
    startd8_get_skill_info,
    startd8_use_skill,
    startd8_compare_agents,
    tasks_list,
    tasks_status,
    tasks_run,
    # models
    ListSkillsInput,
    GetSkillInput,
    UseSkillInput,
    CompareAgentsInput,
)

if __name__ == "__main__":
    mcp.run()
```

This ensures:

- Cursor configs pointing at `startd8_mcp.py` still work
- tests importing `import startd8_mcp` still work

### Step 3: Add `python -m startd8_mcp_server` entrypoint

Create `startd8_mcp_server/__main__.py`:

```python
from .app import mcp

if __name__ == "__main__":
    mcp.run()
```

---

## Worktree boundaries

**FG01 should be the only group doing these edits:**

- moving code between files
- renaming modules
- changing import paths

Other feature groups should only touch code inside their modules.

---

## Acceptance criteria

- `python startd8_mcp.py` still starts the server.
- Existing tests still pass (or only require import-path updates).
- No tool names change.
- No behavior changes (FG01 is refactor-only).

---

## Deliverables

- new `startd8_mcp_server/` package per layout above
- updated `startd8_mcp.py` shim
- minimal docs update: “new internal module layout” (optional)
