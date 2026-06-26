# Agentic Concierge — Provider/Model Config — Plan

**Version:** 1.0 (Post-planning, paired with Requirements v0.2)
**Date:** 2026-06-26
**Status:** Implemented (2026-06-26) — `concierge_agent.py` resolver + `build-preferences.yaml`
`concierge_agent` key + global `~/.startd8` preference + 3 CLI surfaces wired; 9 unit tests green.
**Requirements:** `AGENTIC_CONCIERGE_PROVIDER_CONFIG_REQUIREMENTS.md` (v0.2) →
folded into `AGENTIC_CONCIERGE_MODE_REQUIREMENTS.md` (v0.4)

> **Headline.** A thin read over existing config + one precedence helper — *but* two v0.1
> assumptions were wrong: (1) `build-preferences.yaml` is parsed only as a round-trip validator
> during prose extraction, with **no live read** in the chat path (`build_preferences.py:61`;
> `extract.py:268`), so the resolver must read+parse the file itself; and (2) `resolve_agent_spec`
> does **not** accept catalog tiers (`agent_resolution.py:100-157`) — so the config value is a full
> agent **spec**, not a tier, and `model_routing` (whose tiers are the combined `<provider>-flagship`
> form nothing parses back) is **not** reused.

## Milestones

### M1 — Config readers (no behavior change)
- **FR-PC-2:** add a new top-level `concierge_agent: Optional[str]` to the build-preferences manifest
  + the closed `_TOP_LEVEL_KEYS` allowlist + a parse line — `kickoff_inputs/build_preferences.py:22,33,85`.
  (A new top-level key is required because the allowlist rejects unknown top-level keys; sub-keys are
  open but `model_routing` is semantically wrong for an agent spec.)
- **FR-PC-3 / OQ-5:** add a `concierge_agent` default to `_default_config()["preferences"]` +
  thin `get/set` wrappers over the generic preference store — `config.py:100-104,298-308`.
- Depends on: nothing.

### M2 — The precedence helper (the core)
- **FR-PC-1/4/8/9/10:** new `resolve_concierge_agent_spec(project_root, flag) -> (spec, source)` in
  `src/startd8/kickoff_experience/concierge_agent.py`. Order (first present, non-placeholder wins):
  1. `flag` (the `--agent` value) → source `"flag"`
  2. `<project_root>/docs/kickoff/inputs/build-preferences.yaml` (FR-PC-8: that path only) →
     `parse_build_preferences(text).concierge_agent` → source `"project"`. Wrapped in try/except so a
     **malformed** file is *skipped* (degrade to next layer) + a warning, never fatal (FR-PC-9).
  3. global `get_preference("concierge_agent")` → source `"global"`
  4. `Models.CLAUDE_SONNET_LATEST` → source `"default"` (FR-PC-6 — a catalog reference, no literal).
  - **FR-PC-10:** an angle-bracket placeholder (`<provider:model>`, the template default) is treated
    as unset (skip the layer).
  - Returns the **string only** — it does NOT call `resolve_agent_spec`/validate (FR-PC-5/OQ-6).
- Depends on: M1.

### M3 — Wire the three surfaces
- **FR-PC-1/4/7 (CLI):** in `chat_cmd` (`cli_kickoff.py:245`) and `concierge_chat_cmd` (`:293`),
  replace `spec = agent or Models.CLAUDE_SONNET_LATEST` with
  `spec, source = resolve_concierge_agent_spec(project, agent)` and append the source to the printed
  `agent:` line (`:263,311`).
- **FR-PC-1/4/7 (web):** in `start_cmd` (`cli_kickoff.py:220`), resolve before `make_chat_factory` and
  print spec+source in the agentic-chat status line. `serve.py`/`make_chat_factory` stay unchanged
  (still take a resolved `agent_spec` string) — the resolver runs in the CLI layer, preserving the
  degrade boundary (FR-PC-5).
- **FR-PC-11:** apply to all three surfaces (read-only `chat` shares the same `concierge_agent` key so
  the user's chosen model is consistent across both chat surfaces).
- Depends on: M2.

### M4 — Tests (no live LLM)
- Unit-test `resolve_concierge_agent_spec` across the four precedence layers + the malformed-file
  degrade + the placeholder-ignore, asserting `(spec, source)` only (a temp project dir +
  `ConfigManager(config_dir=tmp)`; the ctor accepts a dir, `config.py:30`). No provider calls.
- FR-PC-5 regression: a configured-but-unresolvable spec still hits the existing CLI actionable-error
  path (resolver returns the bad string; `resolve_agent_spec` raises; the existing except prints).
- Build-preferences round-trip: a `concierge_agent` value survives parse (the new key is extracted).

## Open questions still open
None — all resolved (see Requirements §0).
