# Agentic Concierge — Provider/Model Config Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-26
**Status:** Draft
**Owner:** neil-the-nowledgeable
**Plan:** `AGENTIC_CONCIERGE_PROVIDER_CONFIG_PLAN.md` (v1.0)
**Folds into:** `AGENTIC_CONCIERGE_MODE_REQUIREMENTS.md` (→ v0.4, §E)
**Related:** `model_catalog.py`, `utils/agent_resolution.py`, `kickoff_inputs/build_preferences.py`,
`config.py`

---

## 0. Planning Insights (Self-Reflective Update)

> The planning pass read the real config/parse/resolve code. The feature is a thin read over existing
> config + one precedence helper, but two v0.1 assumptions were wrong and 4 requirements were missing.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| **FR-PC-1:** the config value could be a catalog **tier** "`resolve_agent_spec` already accepts" | `resolve_agent_spec` accepts alias / `provider:model` / provider / model-id **only — NOT tiers** (`agent_resolution.py:100-157`); tiers resolve only via `get_latest_model(provider, tier)` in a split form | **Narrowed FR-PC-1** — config value is a full agent **spec**, no tier support. |
| **OQ-1:** maybe carry the spec in `model_routing` | `model_routing` tiers are the combined `<provider>-flagship` form that nothing parses back and `resolve_agent_spec` can't consume | **OQ-1 → a NEW `concierge_agent` key**, not `model_routing`. |
| **OQ-2:** `build-preferences.yaml` is parsed into something the chat path can read | `parse_build_preferences` exposes `model_routing`, but runs only as a **round-trip validator** during prose extraction (`extract.py:268`) — **no live read** in the chat path | **OQ-2 → the resolver reads+parses the file itself** (a new top-level key extracted by the parser). |
| New top-level key is a free add | `_TOP_LEVEL_KEYS` is a **closed allowlist** that rejects unknown top-level keys (`build_preferences.py:21`) | **Added work:** extend the allowlist + the manifest field (M1). |
| Validation timing was open (OQ-6) | Degrade paths already exist (CLI try/except; `make_chat_factory→None`) | **OQ-6 → resolver returns the string only; validation stays at the existing sites** (FR-PC-5 unchanged). |
| Global config can hold the value (OQ-5) | Generic `get/set_preference` exists; no `concierge_agent` key | **OQ-5 → add a `concierge_agent` preference** (small addition). |

**Resolved open questions:**
- **OQ-1 → new `concierge_agent` key** (not `model_routing`).
- **OQ-2 → resolver reads+parses `docs/kickoff/inputs/build-preferences.yaml`** (no live read existed).
- **OQ-3 → full agent spec, no tier** (`resolve_agent_spec` rejects tiers).
- **OQ-4 → one helper `resolve_concierge_agent_spec(project_root, flag) -> (spec, source)`** in
  `kickoff_experience/concierge_agent.py`; returns the chosen string + source, does not validate.
- **OQ-5 → add a `concierge_agent` preference** in `~/.startd8/config.json`.
- **OQ-6 → validate at the existing sites only** (resolver returns the string; degrade unchanged).

---

## 1. Problem Statement

The agentic Concierge picks its LLM only from the `--agent` CLI flag, defaulting to a hardcoded
catalog constant:

| Surface | How the provider/model is chosen today | Gap |
|---------|----------------------------------------|-----|
| `kickoff chat` / `concierge-chat` | `agent or Models.CLAUDE_SONNET_LATEST` → `resolve_agent_spec(spec)` | No persistent choice — the user must pass `--agent provider:model` every time |
| `kickoff start --agent` (web panel) | same | same |
| Default | `Models.CLAUDE_SONNET_LATEST` (anthropic:claude-sonnet-4-6) | A user who prefers OpenAI/Gemini/Ollama must remember the flag on every invocation |

There is **no config-file way** to say "for this project (or globally), the agentic Concierge uses
`<provider:model>`." Meanwhile the project already ships a per-project model config surface —
`docs/kickoff/inputs/build-preferences.yaml` has a `model_routing` block (`lead_tier`/`drafter_tier`/
`complexity_routing`) — and the SDK has a global config at `~/.startd8/config.json`. Neither is wired
to the agentic Concierge.

**What should exist:** a **config-file-driven provider/model selection** for the agentic Concierge,
so the user sets it once (per project and/or globally) and every chat surface honors it — with the
`--agent` flag still winning as an explicit override, and graceful degradation when the configured
spec can't be resolved.

---

## 2. Requirements

- **FR-PC-1 — Config-file provider/model selection** *(v0.2: full spec, no tier)*. The agentic
  Concierge resolves its agent from a config-file value that is a **full agent spec string**
  (`provider:model`, a bare provider name, a model id, or a legacy alias — anything
  `resolve_agent_spec` accepts), not only the `--agent` flag. **Tier strings are NOT supported**
  (`resolve_agent_spec` does not accept them).
- **FR-PC-2 — Per-project config in `build-preferences.yaml`.** The per-project home is the existing
  `docs/kickoff/inputs/build-preferences.yaml` (the project's build/model preferences). Add a key for
  the agentic-Concierge agent (e.g. under `model_routing` or a sibling `agentic_concierge:` /
  `concierge_agent:` key) carrying the spec. The agentic Concierge is project-scoped (it onboards a
  project), so per-project is the primary surface.
- **FR-PC-3 — Optional global default.** A global default in `~/.startd8/config.json` (the SDK config)
  applies when no per-project value is set — a user's preferred provider across projects.
- **FR-PC-4 — Precedence.** Explicit `--agent` flag **>** per-project config (`build-preferences.yaml`)
  **>** global config (`~/.startd8/config.json`) **>** catalog default (`Models.CLAUDE_SONNET_LATEST`).
  The first present, resolvable value wins.
- **FR-PC-5 — Graceful degradation (unchanged behavior).** When the resolved spec is unresolvable
  (unknown provider) or its key is missing, behavior is exactly as today: the CLI prints an actionable
  error (not a traceback), and the web panel shows the "chat not enabled" notice. The config never
  causes a hard crash.
- **FR-PC-6 — No hardcoded model strings.** The catalog default stays a `model_catalog` reference
  (not a literal). Where the config value is a *tier* (e.g. `balanced`/`flagship`), it resolves
  through `model_catalog` rather than a pinned version string (repo rule).
- **FR-PC-7 — Discoverability.** The chat surfaces report which spec they resolved and its source
  (flag / project-config / global-config / default), so the user can see why a given model was used.

### Surfaced by planning (new in v0.2)

- **FR-PC-8 — Pinned project-config path.** The per-project config is read from
  `<project_root>/docs/kickoff/inputs/build-preferences.yaml` **only** (not the `examples/` /
  `concierge_templates/` copies of the same filename).
- **FR-PC-9 — Malformed project config is non-fatal.** `parse_build_preferences` loud-fails by design;
  a malformed `build-preferences.yaml` must be **skipped** (degrade to the next precedence layer) with
  a warning, never crash resolution.
- **FR-PC-10 — Placeholder values are unset.** The template ships a placeholder (e.g.
  `concierge_agent: <provider:model>`); an angle-bracket placeholder is treated as **unset** (skip the
  layer), never a literal spec.
- **FR-PC-11 — Both chat surfaces share the key.** The read-only `kickoff chat` and the agentic
  `concierge-chat` / web panel resolve from the **same** `concierge_agent` config, so the user's chosen
  model is consistent across both (the `--agent` flag still overrides per-invocation).

---

## 3. Non-Requirements

- **NR-1 — Not a new secrets path.** API keys still come from env vars / the Doppler backend; this
  requirement selects the *provider/model*, not the *key*.
- **NR-2 — Not a new config framework.** Reuse `build-preferences.yaml` + `~/.startd8/config.json`;
  do not invent a third config file unless planning shows neither fits.
- **NR-3 — Not per-turn / runtime switching.** The agent is fixed at session/app construction;
  switching models mid-conversation is out of scope.
- **NR-4 — Does not change `resolve_agent_spec` or the provider set.** Reuse the existing 10-provider
  resolution as-is.

---

## 4. Open Questions

*All 6 resolved by the planning pass — see §0. Retained for the record.*

- **OQ-1 — RESOLVED → new `concierge_agent` key** (not `model_routing`; its tiers are an unparsed
  combined `<provider>-flagship` form).
- **OQ-2 — RESOLVED → the resolver reads+parses `docs/kickoff/inputs/build-preferences.yaml`** (the
  parser exists but only as a round-trip validator — no live read in the chat path today).
- **OQ-3 — RESOLVED → full agent spec, no tier** (`resolve_agent_spec` rejects tiers).
- **OQ-4 — RESOLVED → one helper `resolve_concierge_agent_spec(project_root, flag) -> (spec, source)`**
  in `kickoff_experience/concierge_agent.py`.
- **OQ-5 — RESOLVED → add a `concierge_agent` preference** in `~/.startd8/config.json`.
- **OQ-6 — RESOLVED → resolver returns the string only; validation stays at the existing sites**
  (CLI try/except + `make_chat_factory→None`), so FR-PC-5 is unchanged.

---

*v0.2 — Post-planning self-reflective update. 1 requirement narrowed (FR-PC-1 → spec, no tier), 4
added (FR-PC-8..11), 6 of 6 open questions resolved. Thin read over existing config + one precedence
helper; reuses `build-preferences.yaml` (new `concierge_agent` key) + `~/.startd8/config.json`. To be
folded into `AGENTIC_CONCIERGE_MODE_REQUIREMENTS.md` v0.4 (§E).*
