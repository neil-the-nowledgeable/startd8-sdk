# Flagship Default-Agent Selection — Implementation Plan

**Version:** 1.0 (Post-planning)
**Date:** 2026-06-29
**Tracks requirements:** `FLAGSHIP_DEFAULT_AGENT_REQUIREMENTS.md` v0.2

---

## 0. Planning discoveries (feed the requirements §0)

| v0.1 assumed | Planning revealed | Impact |
|---|---|---|
| FR-1 may need a new flagship resolver | `get_latest_model(provider,'flagship')` is a **hardcoded curated `tier_map`** that already returns the exact D-1/D-2 set (opus-4-8 / gpt-5.5 / 2.5-pro / large / deepseek-chat). | FR-1 narrows to **adopt + name**, not build. |
| FR-3 may need a `stable:bool` field / preview filter | There is **no preview metadata**; stability is guaranteed by the maintainer *choosing a stable constant*. The only enforceable artifact is a **test** asserting the flagship constant isn't a preview. | FR-3 reframed: enforce by **curation + regression test**, not metadata. |
| FR-5: "potentially several" server sites use `supported_models[0]` | **Exactly one** site does (line 3328, `tasks_run`). `use_skill` is **Anthropic-locked** (Claude `SkillAgent`, not per-vendor); `compare_agents` is a **stub**; per-call `model` already exists on skill inputs. | FR-5 narrows to one site; scope shrinks. |
| Agent name ≈ provider name | The server's **default `DEFAULT_AGENT=claude` resolves to `None`** — `get_provider("claude")`/`get_latest_model("claude",…)` both fail; only `anthropic`/`openai`/`gemini` work. `gpt4` preset likewise. | **NEW requirement**: agent-name → provider normalization (FR-10). Without it the default agent has no flagship. |
| Override env name TBD | No existing model env var; only `DEFAULT_AGENT`/`ALLOWED_AGENTS`. `DEFAULT_MODEL` pairs cleanly (no collision). | FR-6 env = `DEFAULT_MODEL`. |
| Catalog availability in server uncertain (OQ-6) | `from startd8.model_catalog import get_latest_model` works in the server's SDK-injected context; returns `gemini:gemini-2.5-pro`. | FR-1 adoption is safe in-server. |

---

## 1. Milestones

### M0 — Catalog as explicit single source of truth (FR-1, FR-2, FR-3, FR-10)
- **`src/startd8/model_catalog.py`**
  - Add `get_flagship(provider: str) -> Optional[str]` — thin, explicitly-named wrapper over
    `get_latest_model(provider, tier="flagship")`. Docstring states the policy: *"the newest
    **stable** model per vendor; previews are never flagship; Anthropic flagship is Opus 4.8, not
    Fable-5 (Fable is a distinct higher class, available only by explicit override)."*
  - Add `canonical_provider(name: str) -> Optional[str]` — normalizes agent/preset aliases to
    provider names: `claude→anthropic`, `gpt4|gpt|gpt-4→openai`, plus identity for known providers.
    Returns `None` for unknown (caller raises explicitly — FR-4).
  - Add a module-level **flagship table comment** ("what loads for vendor V and why") so the catalog
    answers the question standalone (FR-2).
- **Test** `tests/unit/test_model_catalog_flagship.py`
  - Each provider's `get_flagship` is non-`None`, equals the D-set, and the model id contains **no**
    `preview|exp|-pre|alpha|beta` substring (FR-3 enforcement).
  - `canonical_provider` maps the aliases above; unknown → `None`.

### M1 — Server flagship resolution (FR-5, FR-9, FR-10)
- **`mcp/startd8-mcp-builder/startd8_mcp.py`**
  - Normalize `agent_name` via `canonical_provider()` **before** `get_provider()` (line ~3320) so the
    default `claude`/`gpt4` resolve. (Keep the original name for error messages.)
  - Replace line 3328 `model = provider.supported_models[0]…` with a new helper
    `_resolve_default_model(provider_name, provider, per_call_model)` (see M2). The no-override
    branch returns `get_flagship(provider_name)`'s model component.
  - If `get_flagship` returns `None` (unknown/local-only) → explicit error, **no** silent
    `supported_models[0]` fallback (FR-4).

### M2 — Override escape hatch (FR-6, FR-7)
- **`startd8_mcp.py`**
  - Add `model: Optional[str]` to `TaskRunInput` (the DEFAULT_AGENT/`tasks_run` path).
  - `_resolve_default_model` precedence: **per-call `model` > `os.getenv("DEFAULT_MODEL")` >
    `get_flagship(provider)`**. Return `(model, source)` where source ∈
    `{per-call-override, env-override, flagship-default}`.
  - Validate the chosen model ∈ `provider.supported_models`; on miss → explicit error listing the
    allowed models (FR-7). Flagship-default is trusted (already a supported model) but still
    asserted defensively.

### M3 — "What loaded and why" observability (FR-8)
- **`startd8_mcp.py`**
  - Emit one quiet-respecting log line on resolution: `model.resolved provider=… model=… source=…`.
  - Extend the `startd8_status` tool (~line 2913, already reports `DEFAULT_AGENT`) to also report the
    **resolved default model + source** for the active default agent, and the `DEFAULT_MODEL` override
    (masked if unset).

### M4 — Verification
- Run M0 unit test (repo `.venv`).
- Server-side checks via the home `.venv` + `PYTHONPATH=src`: default agent → flagship;
  `DEFAULT_MODEL=gemini-2.5-flash` env override; per-call `model`; invalid model → listed error.
- `test_13_skill_tool_registration.py` still green (no regression to tool registration).

---

## 2. Files touched
- `src/startd8/model_catalog.py` (add `get_flagship`, `canonical_provider`, flagship comment table)
- `mcp/startd8-mcp-builder/startd8_mcp.py` (normalize + `_resolve_default_model` + `TaskRunInput.model` + status/log)
- `tests/unit/test_model_catalog_flagship.py` (new)
- (server test) `mcp/startd8-mcp-builder/tests/test_14_flagship_resolution.py` (new, optional but recommended)

## 3. Risks / notes
- **R-1 Two homes.** The catalog change lands in `src/`; the server reads `src/` of whatever worktree
  it runs from. Land on `main`, and the `startd8-mcp-server` home (tracks main) picks it up after a
  pull. Don't edit only one tree.
- **R-2 `DEFAULT_AGENT=claude` default.** Normalization fixes resolution, but consider whether the
  server's *documented default* should become `anthropic` for clarity. Non-breaking either way once
  `canonical_provider` exists. (Requirements: see FR-10 note.)
- **R-3 Out of scope (NR-1/NR-2):** not reordering `supported_models`; other SDK default-agent sites
  remain governed by `MODEL_CONFIG_FIRST_CLASS_REQUIREMENTS.md`.
