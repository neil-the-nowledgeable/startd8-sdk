# Refactor Plan: `startd8_use_skill` JSON-First with Metrics

## Context and Goal

The current `startd8_use_skill` tool in `startd8_mcp.py`:

- Loads a `SKILL.md` file as the **system prompt**,
- Calls Anthropic (Claude) with that system prompt + a user `prompt`,
- Returns a **Markdown-formatted string** that includes:
  - Skill name,
  - Model name,
  - Token usage (from `message.usage`),
  - The generated text.

We are **refocusing Startd8 SDK + MCP** so the MCP acts as a **programmatic harness** for running skills/agents and capturing their **outputs plus resource usage** (tokens, time, etc.). Any analysis/benchmarking will be done **outside** the MCP, by callers that consume this data.

**Design decision:**

- We will **evolve the existing `startd8_use_skill` tool** (Option A), instead of adding a separate tool.
- The tool will become **JSON-first**, with Markdown as a **view** on that JSON.

This document is the implementation plan for that refactor.

---

## 1. Canonical JSON Schema (Result Shape)

`startd8_use_skill` should always build a **canonical Python dict** internally, then serialize it either as JSON or Markdown depending on `response_format`.

### Proposed top-level schema

```jsonc
{
  "skill_name": "mcp-builder",        // Resolved name from SKILL.md or directory
  "skill_directory": "/path/to/skill", // Directory where SKILL.md lives
  "model": "claude-sonnet-4-20250514", // Final model actually used
  "prompt": "user prompt string",       // Prompt sent as the user message
  "output": "model-generated text",     // Main text output from the model
  "response_format": "json",            // "json" or "markdown" (echo of input)

  "usage": {
    "input_tokens": 1234,
    "output_tokens": 567,
    "total_tokens": 1801
  },

  "timing": {
    "started_at": "2025-12-09T10:00:00Z",   // ISO 8601 UTC
    "completed_at": "2025-12-09T10:00:02Z", // ISO 8601 UTC
    "latency_ms": 2000
  },

  "sdk": {
    "version": null,               // Placeholder for Startd8 SDK version, if known
    "run_id": null,                // Placeholder for any SDK-internal run ID
    "provider": "anthropic"       // e.g., "anthropic"
  },

  "metadata": {
    // Free-form: anything else useful (e.g., env, config flags)
  },

  "error": null                     // Reserved for a future structured error shape
}
```

### Notes

- **Backward compatibility:** For now, `startd8_use_skill` will still **return plain error strings** on failure, as it does today. The `error` field is forward-looking, for the day we want to return structured errors in JSON mode.
- **Stability:** New fields can be added under `sdk`, `usage`, `metadata`, or `error` without breaking callers that just parse and pick the keys they need.

Developers should **document this schema** in `README_SERVER.md` or similar when implementing it, including at least one full example for Markdown and one for JSON.

---

## 2. `UseSkillInput` Changes (Design)

Existing model in `startd8_mcp.py`:

```python
class UseSkillInput(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    skill_name: str = Field(...)
    prompt: str = Field(...)
    model: Optional[str] = Field(default="claude-sonnet-4-20250514")
    max_tokens: Optional[int] = Field(default=16384, ge=1, le=200000)
    track_response: bool = Field(default=True)
```

### Planned additions

1. **Add response_format field** using existing `ResponseFormat` enum:

```python
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description=(
            "Output format: 'markdown' for human-readable summary "
            "or 'json' for structured metrics and output."
        ),
    )
```

2. **Keep existing behavior**:
   - Default remains `markdown` to avoid surprises in any existing flows.
   - `extra='forbid'` stays, so unexpected fields still error.

*(Optional for later)*: If you want to later include full skill instructions in JSON, you can consider an additional flag such as:

```python
    include_raw_instructions: bool = Field(
        default=False,
        description="If true, include the full SKILL.md instructions in the JSON metadata.",
    )
```

For the initial refactor, this is not strictly necessary.

---

## 3. `startd8_use_skill` Refactor Steps

This section is the **step-by-step guide** for modifying the implementation, once we are ready to change code.

### 3.1. Measure timing

Inside `startd8_use_skill`, around the Anthropic call:

1. Before calling `client.messages.create(...)`:

   ```python
   import time
   from datetime import datetime, timezone

   started_at = datetime.now(timezone.utc)
   start_perf = time.perf_counter()
   ```

2. After the response is received:

   ```python
   completed_at = datetime.now(timezone.utc)
   latency_ms = int((time.perf_counter() - start_perf) * 1000)
   ```

3. Convert to ISO strings for JSON:

   ```python
   started_at_iso = started_at.isoformat().replace("+00:00", "Z")
   completed_at_iso = completed_at.isoformat().replace("+00:00", "Z")
   ```

### 3.2. Extract usage from Anthropic response

Given the current code uses `message = client.messages.create(...)` and then:

```python
response_text = message.content[0].text
# message.usage.input_tokens, message.usage.output_tokens
```

Construct a usage dict:

```python
usage = {
    "input_tokens": getattr(message.usage, "input_tokens", None),
    "output_tokens": getattr(message.usage, "output_tokens", None),
    "total_tokens": None,
}

if usage["input_tokens"] is not None and usage["output_tokens"] is not None:
    usage["total_tokens"] = usage["input_tokens"] + usage["output_tokens"]
```

### 3.3. Build the canonical result dict

After successfully getting `message` and `response_text` and having `skill` and `instructions` available, construct:

```python
result = {
    "skill_name": skill["name"],
    "skill_directory": skill.get("directory"),
    "model": params.model,
    "prompt": params.prompt,
    "output": response_text,
    "response_format": params.response_format.value,
    "usage": usage,
    "timing": {
        "started_at": started_at_iso,
        "completed_at": completed_at_iso,
        "latency_ms": latency_ms,
    },
    "sdk": {
        "version": None,      # To be filled when SDK exposes it
        "run_id": None,       # Optional future integration
        "provider": "anthropic",
    },
    "metadata": {},
    "error": None,
}
```

### 3.4. Format based on `response_format`

1. **JSON mode** (`params.response_format == ResponseFormat.JSON`):

   ```python
   return json.dumps(result, indent=2)
   ```

2. **Markdown mode** (`ResponseFormat.MARKDOWN`):

   Build a Markdown string derived from `result`:

   ```markdown
   # Response from <skill_name>

   **Model:** <model>
   **Tokens:** <input_tokens> in, <output_tokens> out (total <total_tokens>)
   **Latency:** <latency_ms> ms

   ---

   <output>
   ```

   This keeps the current UX but makes it explicitly a **view over the JSON**. Implementation sketch:

   ```python
   lines = [
       f"# Response from {result['skill_name']}",
       "",
       f"**Model:** {result['model']}",
   ]

   if result["usage"]["input_tokens"] is not None and result["usage"]["output_tokens"] is not None:
       lines.append(
           f"**Tokens:** {result['usage']['input_tokens']} in, "
           f"{result['usage']['output_tokens']} out (total {result['usage']['total_tokens']})"
       )

   lines.append(f"**Latency:** {result['timing']['latency_ms']} ms")
   lines.append("")
   lines.append("---")
   lines.append("")
   lines.append(result["output"])

   return "\n".join(lines)
   ```

### 3.5. Error behavior (for now)

For this first refactor pass, **do not change error behavior**:

- Keep returning **plain error strings** (as today) for:
  - Missing skill,
  - Missing `ANTHROPIC_API_KEY`,
  - Missing `anthropic` SDK,
  - API errors.

Later, if we decide to support structured errors in JSON mode, we can:

- Detect `response_format == ResponseFormat.JSON` and return a JSON object with `error` populated, instead of a plain string.

---

## 4. Test Suite Changes (Planned)

The existing tests live under `tests/`. These are the planned changes—**do not implement yet**, this is the checklist.

### 4.1. `tests/test_05_use_skill.py`

1. **Success with mocked Anthropic (JSON mode)**

   - Update or add a test that calls:

     ```python
     result = await startd8_mcp.startd8_use_skill(
         UseSkillInput(
             skill_name="skill-test-1",
             prompt="Test prompt",
             model="claude-test-model",
             max_tokens=1234,
             response_format=ResponseFormat.JSON,
         )
     )
     data = json.loads(result)
     ```

   - Assert on:
     - `data["skill_name"] == "skill-test-1"`
     - `data["model"] == "claude-test-model"`
     - `data["prompt"] == "Test prompt"`
     - `data["output"] == "fake-response"` (from `mock_anthropic_api`)
     - `data["usage"]["input_tokens"]` / `output_tokens` and `total_tokens` values from the mock
     - `data["timing"]["latency_ms"]` is an `int` and `>= 0`

2. **Markdown mode still works and includes metrics**

   - Add a separate test using `response_format=ResponseFormat.MARKDOWN` and assert:
     - String starts with `"# Response from skill-test-1"`
     - Contains `"**Model:** claude-test-model"`
     - Contains `"**Tokens:"` and a sensible token string
     - Contains `"**Latency:"` and `"ms"`

### 4.2. `tests/test_06_input_validation.py`

- Add validation tests around the new `response_format` field:

  ```python
  UseSkillInput(skill_name="ok", prompt="hi", response_format=ResponseFormat.JSON)
  UseSkillInput(skill_name="ok", prompt="hi", response_format="markdown")

  with pytest.raises(ValidationError):
      UseSkillInput(skill_name="ok", prompt="hi", response_format="invalid")
  ```

This ensures Pydantic enforces allowable formats.

### 4.3. `tests/test_12_workflows.py`

- For at least one workflow (e.g., `test_full_skill_usage_workflow`):
  - Switch the final `startd8_use_skill` call to JSON mode.
  - Parse the JSON and assert that:
    - `usage` and `timing` blocks are present.
    - The complex prompt appears in `prompt`.
    - `output` is the mock response.

This gives an end-to-end guarantee that workflows can consume metrics programmatically.

---

## 5. Documentation and Migration Notes

When implementing this refactor, please also:

1. **Update `README_SERVER.md` (or similar)**
   - Document the new `response_format` parameter on `startd8_use_skill`.
   - Provide two examples:
     - Markdown response example (for humans / interactive use).
     - JSON response example (for programmatic benchmarking / evaluation).

2. **Explain the role of MCP vs SDK**
   - Clarify that the MCP server:
     - Exposes SDK skills as MCP tools.
     - Returns **raw outputs + metrics**.
     - Does **not** perform analysis or scoring itself.

3. **Keep defaults stable**
   - Default `response_format` is `markdown`.
   - Existing consumers that expect markdown output should continue to work without changes.

4. **Future extension (not in this refactor)**
   - Structured error objects in JSON mode using the `error` field.
   - Filling `sdk.version`, `sdk.run_id`, and more detailed provider data once the Startd8 SDK exposes them.

---

## Summary for Implementers

- **Do first:**
  - Add `response_format` to `UseSkillInput` (default `markdown`).
  - Refactor `startd8_use_skill` to build a canonical result dict, with timing and token usage.
  - Branch on `response_format` to return either JSON or Markdown.

- **Then:**
  - Update unit tests (`test_05_use_skill.py`, `test_06_input_validation.py`) and workflow tests (`test_12_workflows.py`) to assert on the new JSON structure and markdown metrics.

- **Finally:**
  - Update documentation to clearly describe the new behavior and provide examples.

This plan is intentionally detailed so that any developer (or future AI assistant) can implement the changes step-by-step without needing additional context.