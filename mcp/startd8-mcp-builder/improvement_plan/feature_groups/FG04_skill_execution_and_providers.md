# FG04 — Skill Execution and Providers (SDK + Anthropic Fallback)

## Goal

Make `startd8_use_skill` (and future execution tools) reliable and extensible by introducing a clear execution abstraction:

- choose **SDK-backed execution** when Startd8 SDK is available and correctly configured
- otherwise use a clean **Anthropic fallback**
- implement `track_response` in a principled way
- remove the MCP placeholder and implement `startd8_compare_agents`
- eliminate brittle global logging monkeypatches

This group also directly addresses the recurring “wrong server env / abstract class” issue.

---

## Current pain points

- Execution path selection is intertwined with logging workarounds.
- The “abstract class ClaudeSkillAgent” failure is often caused by **PYTHONPATH drift** between the dev shell and the MCP client.
- Logging collision fixes are applied globally and redundantly.

---

## Design: Provider interface

Create `startd8_mcp_server/skills/execution.py`:

### Provider protocol

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol


@dataclass(frozen=True)
class GenerationResult:
    output: str
    usage: Dict[str, Any]
    timing: Dict[str, Any]
    provider: str
    metadata: Dict[str, Any]


class Provider(Protocol):
    name: str

    def generate(self, *, system: str, prompt: str, model: str, max_tokens: int) -> GenerationResult:
        ...
```

### Anthropic provider

- encapsulate Anthropic calls
- sanitize logging **locally** (no global record-factory patches)

```python
class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def generate(self, *, system: str, prompt: str, model: str, max_tokens: int) -> GenerationResult:
        # import anthropic here
        # call client.messages.create
        # return GenerationResult
        ...
```

### SDK provider

- uses Startd8 SDK SkillAgent implementation
- must never instantiate abstract aliases

```python
class Startd8SdkProvider:
    name = "startd8-sdk"

    def __init__(self, sdk_path: Optional[str]):
        # ensure SDK importable
        ...

    def generate(self, *, system: str, prompt: str, model: str, max_tokens: int) -> GenerationResult:
        # construct SkillAgent with skill_id + system prompt, call generate
        ...
```

---

## Execution selection rules

- If `STARTD8_FORCE_ANTHROPIC_FALLBACK=1` → always Anthropic.
- Else if SDK import succeeds AND a concrete SkillAgent is available → use SDK.
- Else → Anthropic.

All selection decisions should be returned in response metadata:

```json
"data": {
  "execution": {
    "selected_provider": "startd8-sdk",
    "sdk_available": true,
    "forced_fallback": false
  }
}
```

---

## Fix: “wrong env” / abstract class mismatch

### Design

Add a diagnostics tool (read-only), e.g. `startd8_diagnostics`, that returns:

- effective `sys.path`
- resolved SDK module paths
- resolved agent class (type + module)
- key env vars relevant to resolution

**Example payload:**

```json
{
  "data": {
    "python": {"executable": "...", "version": "..."},
    "env": {"STARTD8_SDK_PATH": "...", "PYTHONPATH": "..."},
    "sdk": {"import_ok": true, "startd8_module": "..."},
    "skill_agent": {"resolved": true, "class": "SkillAgent", "module": "startd8.skills.agent"}
  }
}
```

### Operational fix

Make `run_mcp.sh` (already present) the **canonical launcher** and update Cursor config to call it via `/bin/sh -lc` so the same env is used in Cursor and in your shell.

---

## Implement `track_response`

### Behavior

- If SDK is available and framework storage is configured: store prompt/response + metrics.
- If SDK is absent: return metadata indicating it was skipped.

**Example:**

```json
"data": {
  "tracking": {"requested": true, "performed": false, "reason": "sdk_unavailable"}
}
```

---

## Worktree boundaries

Expected files changed (post-FG01 module split):

- `startd8_mcp_server/skills/execution.py`
- `startd8_mcp_server/logging_utils.py` (only if needed; coordinate with FG06)
- `startd8_mcp_server/tools/use_skill.py` (or wherever the tool lives)
- docs: Cursor config and `run_mcp.sh` usage (coordinate with FG06)

---

## Acceptance criteria

- `startd8_use_skill` deterministically reports which provider was used.
- The abstract-class error becomes a structured “invalid configuration” error with actionable diagnostics.
- `track_response` is implemented when SDK is present and safely skipped otherwise.
- `startd8_compare_agents` no longer returns a placeholder message; it performs an actual comparison and returns structured results.
- No global LogRecord factory monkeypatching is required for normal operation.
