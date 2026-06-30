# Flagship Default-Agent Selection — Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-29
**Status:** Draft
**Owner:** neil-the-nowledgeable
**Plan:** `FLAGSHIP_DEFAULT_AGENT_PLAN.md` v1.0

---

## 0. Planning Insights (Self-Reflective Update)

> The planning pass read the catalog resolver, the MCP server's model-resolution sites, and the
> provider registry. It corrected the draft in 6 places — and surfaced one **new, required** piece
> the draft missed (FR-10). Net: the change is **smaller and more surgical** than v0.1 implied, with
> one sharp gotcha (the default agent name doesn't resolve to a provider at all).

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| FR-1 might need a new flagship resolver | `get_latest_model(provider,'flagship')` is a **hardcoded curated `tier_map`** that already returns the exact chosen set (opus-4-8 / gpt-5.5 / 2.5-pro / large / deepseek-chat). | **FR-1 narrows**: adopt + give it an explicit name; don't build a resolver. |
| FR-3 needs preview metadata / a `stable` field | There is **no preview flag** anywhere; "stable" is guaranteed only by the maintainer *choosing a stable constant*. | **FR-3 reframed**: enforce via **curation + a regression test** that the flagship constant isn't a preview — not via metadata. |
| FR-5: several server sites use `supported_models[0]` | **Exactly one** does (line 3328, `tasks_run`). `use_skill` is **Anthropic-locked**; `compare_agents` is a **stub**. | **FR-5 narrows** to one site. |
| Agent name ≈ provider name | The server's **documented default `DEFAULT_AGENT=claude` resolves to `None`** (so does the `gpt4` preset): `get_provider("claude")` and `get_latest_model("claude",…)` both fail; only `anthropic`/`openai`/`gemini` resolve. | **NEW FR-10**: agent-name → provider normalization. Without it the *default* agent has no flagship — the headline bug is worse than "wrong model": it's "no model". |
| Override env name TBD (OQ-5) | No existing model env var (only `DEFAULT_AGENT`/`ALLOWED_AGENTS`); `DEFAULT_MODEL` pairs cleanly. | FR-6 env name fixed = `DEFAULT_MODEL`. |
| Catalog availability in-server uncertain (OQ-6) | `from startd8.model_catalog import get_latest_model` works in the server's SDK-injected context. | FR-1 adoption is safe in-server. |

**Resolved open questions:**
- **OQ-1 → Reuse, don't build.** `get_latest_model(provider,'flagship')` already returns the D-1/D-2
  set. FR-1 = add an explicitly-named `get_flagship()` wrapper + docs.
- **OQ-2 → No metadata.** Stable-vs-preview is curation, not a field. Enforce with a test (FR-3).
- **OQ-3 → One site** (`tasks_run`, line 3328). `use_skill`=Anthropic-locked, `compare_agents`=stub.
- **OQ-4 → Per-call `model` exists on skill inputs but NOT on `TaskRunInput`** (the flagship path);
  add it (FR-6b).
- **OQ-5 → `DEFAULT_MODEL`** (pairs with `DEFAULT_AGENT`; no collision).
- **OQ-6 → Catalog importable in-server.**

---

## 1. Problem Statement

When a caller selects a vendor (an "agent" like `gemini`) without naming a model, the system must
load that vendor's **flagship** — a well-defined, intentional model. Today it loads
`provider.supported_models[0]`, which is **list-ordering, not a flagship designation**, and is
correct for only 2 of 6 vendors by coincidence:

| Vendor | `supported_models[0]` (loads today) | Intended flagship | Correct? |
|--------|-------------------------------------|-------------------|----------|
| anthropic | `claude-fable-5` | `claude-opus-4-8` | ❌ wrong class |
| openai | `gpt-4.1` | `gpt-5.5` | ❌ **stale** |
| gemini | `gemini-3.1-pro-preview` | `gemini-2.5-pro` | ❌ preview |
| mistral | `mistral-large-latest` | `mistral-large-latest` | ✅ (coincidence) |
| deepseek | `deepseek-chat` | `deepseek-chat` | ✅ (coincidence) |
| ollama | `llama2` | (local; n/a) | ❌ stale |

Worse (planning discovery): the server's **default** agent `claude` doesn't map to a provider at
all, so the default `tasks_run` path can't even resolve a model. A curated single-source-of-truth
catalog already exists (`get_latest_model(provider,'flagship')`); the defect is that default-agent
resolution **doesn't use it** and **doesn't normalize agent names** to provider names.

### Policy decisions (resolved up front by owner)

- **D-1 Flagship = newest *stable*.** Previews/experimental are never flagship (Gemini → `2.5-pro`).
- **D-2 Anthropic flagship = `claude-opus-4-8`.** Fable-5 is a distinct higher "Mythos" class, not the
  default flagship (available only by explicit override).
- **D-3 An override escape hatch exists** to pin an exact supported model without editing the catalog.
- **D-4 Scope = MCP server + the catalog as explicit single source of truth.** Provider
  `supported_models` reordering and an SDK-wide default-agent audit are out of scope (§3).

---

## 2. Requirements

### Catalog as single source of truth

- **FR-1 Adopt + name the canonical flagship resolver.** The catalog MUST expose an explicitly-named
  `get_flagship(provider) -> "provider:model" | None`, a thin wrapper over the existing
  `get_latest_model(provider, tier='flagship')` (which already returns the D-1/D-2 set). No new
  resolution logic is built; the value comes from the named, documented entry point.
- **FR-2 Explicit, documented flagship per vendor.** The catalog MUST state, in-file and
  human-readable, each vendor's selected flagship and *why* ("newest stable"), so a reader can answer
  "what loads for vendor V and why" from the catalog alone. This MUST include the D-2 Fable-vs-Opus
  rationale.
- **FR-3 Preview exclusion is enforced by test, not metadata.** A regression test MUST assert that
  every vendor's `get_flagship` model id contains **no** preview marker
  (`preview|exp|-pre|alpha|beta`) and equals the agreed D-set. (There is no preview metadata field;
  the guarantee is curation + this test. Adding such a field is explicitly NOT required.)
- **FR-4 Unknown/local ⇒ explicit, not silent.** `get_flagship` MUST return `None` for an unknown
  provider, and callers MUST handle `None` with an explicit error — never an arbitrary
  `supported_models[0]` fallback. (All *known* cloud vendors return a value; Ollama is local and
  exempt from the flagship guarantee — FR-9.)

### Agent-name normalization

- **FR-10 Canonical provider mapping.** Default-agent resolution MUST normalize agent/preset aliases
  to provider names before resolving a provider or flagship: at minimum `claude→anthropic`,
  `gpt4|gpt|gpt-4→openai`, and identity for known provider names. An unrecognized name resolves to
  `None` and fails explicitly (FR-4). This is required for the *default* agent (`claude`) to have a
  flagship at all.

### Default-agent resolution (MCP server)

- **FR-5 Default model = catalog flagship.** When the MCP server selects a model for a vendor/agent
  without an explicit model (the `tasks_run` path, the sole `supported_models[0]` site), it MUST
  resolve via `get_flagship(canonical_provider(agent))`, NOT `provider.supported_models[0]`.
- **FR-6 Override escape hatch (D-3).** A caller MUST be able to pin an exact model via
  (a) the `DEFAULT_MODEL` env var, and (b) a per-call `model` field on `TaskRunInput` (which does not
  exist today and MUST be added). Precedence: **per-call `model` > `DEFAULT_MODEL` env > flagship.**
- **FR-7 Override is validated.** An overriding model MUST be validated against the resolved
  provider's `supported_models`; an unknown model fails with an explicit error **listing the allowed
  models** — never a silent fall back to flagship.
- **FR-8 "What loaded and why" is observable.** On resolution the server MUST report the resolved
  `provider:model` AND the source (`flagship-default` | `env-override` | `per-call-override`) in (a)
  a quiet-respecting log line and (b) the `startd8_status` tool output (which already reports
  `DEFAULT_AGENT`).

### Cross-vendor guarantee

- **FR-9 Every cloud vendor resolves to its flagship.** With no override, the resolved default MUST
  equal: anthropic→`opus-4-8`, openai→`gpt-5.5`, gemini→`2.5-pro`, mistral→`large-latest`,
  deepseek→`deepseek-chat`. Ollama is local-only and exempt (FR-4 path).

---

## 3. Non-Requirements

- **NR-1** Does NOT reorder each provider's `supported_models` so `[0]` is the flagship (deferred;
  consumers must use the resolver).
- **NR-2** Does NOT audit/fix every default-agent site SDK-wide (CLI, TUI presets, `compare-models`,
  prime-pipeline roles) — those are governed by `MODEL_CONFIG_FIRST_CLASS_REQUIREMENTS.md`. This slice
  is the MCP server + catalog only.
- **NR-3** Does NOT re-tier Fable vs Opus beyond designating Opus 4.8 the default flagship (D-2).
- **NR-4** Does NOT add new vendors/models. **NR-5** Does NOT change pricing/cost logic.
- **NR-6** Does NOT change `use_skill` (Anthropic-locked by design) or `compare_agents` (stub).

---

## 4. Open Questions

- **OQ-7** Should the server's *documented default* `DEFAULT_AGENT` change from `claude` to
  `anthropic` for clarity, now that FR-10 makes both resolve? (Non-breaking either way; cosmetic.)
- **OQ-8** Override env name: `DEFAULT_MODEL` (chosen) vs a namespaced `STARTD8_MODEL`. Is there a
  consumer expecting one or the other? (Default to `DEFAULT_MODEL`; add `STARTD8_MODEL` as an alias
  only if a need appears.)

*(OQ-1…OQ-6 resolved in §0.)*

---

*v0.2 — Post-planning self-reflective update. 1 requirement added (FR-10), 3 narrowed (FR-1/3/5),
1 env name fixed (FR-6), 6 open questions resolved. The headline correction: the default agent name
doesn't resolve to a provider at all — normalization (FR-10) is load-bearing, not cosmetic.*
