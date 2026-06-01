# Prime Contractor Model Refresh — Requirements

**Version:** 1.0 (Implemented)
**Date:** 2026-06-01
**Status:** Implemented — `tests/unit/test_contractor_model_centralization.py` is the regression guard (REQ-PCMR-130).
**Prefix:** REQ-PCMR (Prime Contractor Model Refresh)
**Related:** REQ-TMM (TUI Model-List Management) — provides the catalog overlay this work routes through.

---

## 1. Problem Statement

The Prime/Primary Contractor construction path should run on the **latest and greatest**
models, and selecting/maintaining those models should happen in **one place**. Today
neither is true:

1. **Stale defaults.** The lead/reviewer role runs on Sonnet 4.6 (`balanced`) and several
   auxiliary paths still name legacy models (`openai:gpt-4o-mini`, `gemini:gemini-2.0-flash`).
2. **Fragmented selection surface.** Model identifiers for the contractor are pinned in at
   least **five** places that do not consult the centralized catalog, so a model refresh
   means editing source in several files and risks drift.

This is the same fragmentation that motivated REQ-TMM, but for the *contractor's* model
choices rather than the *TUI's* picker. REQ-TMM already centralized the catalog and added a
user-editable overlay (`~/.startd8/user_models.json`); this work makes the contractor path
**consume that single source** instead of carrying parallel copies.

### Decisions locked (this revision)

| Decision | Choice | Consequence |
|----------|--------|-------------|
| Lead/reviewer tier | **Upgrade to Opus 4.8 (flagship)** — cost increase acknowledged | `PRIMARY_CONTRACTOR_LEAD` → `CLAUDE_OPUS_LATEST`; reviewer follows (defaults to lead). |
| Drafter | **Stay Gemini Flash Lite** | `PRIMARY_CONTRACTOR_DRAFTER` unchanged (`GEMINI_FLASH_LITE`), kept as a catalog constant. |
| TUI leverage | **Route-through-catalog only** | No new TUI feature. Eliminate parallel lists so every path resolves from `model_catalog`; the existing overlay already flows through it. |
| Blast radius | **All contractor model touchpoints** | One sweep: builtin workflows + contextcore variants + `integrations/contextcore.py` + `config.py` defaults + docstrings. |

---

## 2. Contractor model-source inventory (as found 2026-06-01)

| # | Source | Anchor | Current value | Catalog-backed? |
|---|--------|--------|---------------|-----------------|
| 1 | `Models.PRIMARY_CONTRACTOR_LEAD` | `model_catalog.py:132` | `CLAUDE_SONNET_LATEST` | ✅ (is the catalog) |
| 2 | `Models.PRIMARY_CONTRACTOR_DRAFTER` | `model_catalog.py:133` | `GEMINI_FLASH_LITE` | ✅ (is the catalog) |
| 3 | `PrimaryContractorConfig.lead_agent/drafter_agent` | `primary_contractor_models.py:87-88` | refs #1/#2 | ✅ |
| 4 | `DrafterChoice` enum | `primary_contractor_models.py:36-50` | parallel hardcoded list incl. retiring Gemini 2.0, gpt-4o-mini | ❌ **dead code** (no `src/` consumer) |
| 5 | contextcore workflow default | `primary_contractor_contextcore_workflow.py:30,259` | `openai:gpt-4o-mini` (stale) | ❌ |
| 6 | integration example/default | `integrations/contextcore.py:390` | `openai:gpt-4o-mini` (stale) | ❌ |
| 7 | TUI agent-config defaults | `config.py:71-78` | `claude-sonnet-4-6`, `gpt-4o` | ❌ |
| 8 | Docstring "Recommended …" lists | `primary_contractor_workflow.py:~195-215` and others | mixed legacy (`claude-opus-4-6`, `gpt-4o-mini`) | ❌ (doc drift) |

**Net gap:** the contractor's "what model" decision is spread across 5 non-catalog
locations (#4–#8). #4 is vestigial. #5–#7 are stale hardcodes. #8 is documentation drift.

---

## 3. Requirements

> **Acceptance Criteria (AC)** are compact and testable. "Catalog" = `model_catalog.py`
> (`Models` constants + `get_latest_model()`), inclusive of the REQ-TMM user overlay.

### 3.1 Refresh the defaults to latest/greatest

- **REQ-PCMR-100** — `Models.PRIMARY_CONTRACTOR_LEAD` MUST resolve to the Anthropic flagship
  (`CLAUDE_OPUS_LATEST`, currently `anthropic:claude-opus-4-8`). The reviewer role, which
  defaults to `lead_agent` (`prime_contractor.py:497`), inherits this with no separate edit.
  - **AC:** A `PrimaryContractorConfig()` with no overrides reports `lead_agent ==
    Models.CLAUDE_OPUS_LATEST`; a run with no `review_agent` override uses the same spec.
- **REQ-PCMR-101** — `Models.PRIMARY_CONTRACTOR_DRAFTER` MUST remain a cheap tier and MUST be
  expressed via a catalog constant (not a raw string), so "latest cheap" tracks the catalog.
  Default stays **`GEMINI_FLASH_LITE`** (OQ-A resolved 2026-06-01: keep Gemini Flash Lite).
  - **AC:** `PrimaryContractorConfig().drafter_agent` equals a `Models.*` constant value and is
    present in `_MODEL_REGISTRY` with tier ∈ {`fast`,`mini`}.
- **REQ-PCMR-102** — No `src/startd8` contractor path may pin a model id that is **absent from
  the catalog** or **flagged retiring** (e.g. `gemini-2.0-*`). Cost/quality refresh is a
  one-line catalog edit thereafter.
  - **AC:** A test asserts every contractor-path default spec satisfies `is_known_model(spec)`
    and is not in a `RETIRING` denylist.

### 3.2 Eliminate parallel / stale model lists (route through catalog)

- **REQ-PCMR-110** — The `DrafterChoice` enum (`primary_contractor_models.py`) MUST be removed
  **or** redefined to derive its members from the catalog (`list_models_by_tier("fast"|"mini")`).
  Removal is preferred since it has no `src/` consumer (dead code).
  - **AC:** `grep -rn DrafterChoice src/startd8` returns only (at most) a catalog-derived
    definition; no hand-maintained provider:model literals remain in that enum.
- **REQ-PCMR-111** — The contextcore contractor variants and the integration adapter MUST stop
  hardcoding `openai:gpt-4o-mini`. Their drafter default MUST come from
  `Models.PRIMARY_CONTRACTOR_DRAFTER` (config default), not an inline literal. Example
  snippets in docstrings MUST use a current catalog model.
  - **Anchors:** `primary_contractor_contextcore_workflow.py:30,259`,
    `integrations/contextcore.py:390`.
  - **AC:** Those modules contain no `gpt-4o-mini` literal; omitting `drafter_agent` in their
    config yields `Models.PRIMARY_CONTRACTOR_DRAFTER`.
- **REQ-PCMR-112** — `config.py` TUI agent defaults (`models.claude.default`,
  `models.gpt4.default`) MUST derive from the catalog (`get_latest_model("anthropic","balanced")`
  / `get_latest_model("openai","balanced")` or the relevant `Models.*` constant) rather than
  bare version strings, so a catalog bump updates the TUI default too.
  - **AC:** Changing `CLAUDE_SONNET_LATEST` changes the resolved `models.claude.default` with no
    edit to `config.py`.

### 3.3 Documentation truth

- **REQ-PCMR-120** — All "Recommended Lead/Drafter Agents" docstrings in the contractor
  workflows MUST list only catalog-current models and MUST point readers to `model_catalog.py`
  as the single edit point.
  - **AC:** No contractor docstring names a model absent from `_MODEL_REGISTRY`; each
    "Recommended …" block references `Models.*` / `model_catalog`.

### 3.4 Regression guard (the centralization invariant)

- **REQ-PCMR-130** — A unit test MUST enforce that the contractor path resolves all default
  agent specs through the catalog: it enumerates the known default sites (config defaults,
  workflow defaults, integration default) and asserts each equals a `Models.*` constant and
  passes `is_known_model`. This is the guardrail that keeps the surface from re-fragmenting.
  - **AC:** Introducing a new hardcoded contractor model literal fails this test.

---

## 4. Non-Requirements

- **NR-1** — Will NOT add a new TUI feature (no persisted lead/drafter/reviewer "role defaults"
  UI). Centralization is achieved by routing through the existing catalog + REQ-TMM overlay.
- **NR-2** — Will NOT change `get_latest_model`'s tier→constant mapping or the overlay
  semantics defined by REQ-TMM (NR-6 there still holds: overlay models are resolvable, not
  auto-selected as tier defaults).
- **NR-3** — Will NOT alter the Prime **batch** routing contract: `ComplexityRouter` per-tier
  agent specs and `tier3_agent` remain caller-supplied; this work only ensures their *defaults*
  (when unset) come from the catalog.
- **NR-4** — Will NOT introduce per-run cost caps or budget enforcement (out of scope; cost is
  governed by the chosen tier).
- **NR-5** — Will NOT touch Artisan (ON HOLD) or non-contractor workflows
  (doc-enhancement, policy-analysis, etc.) except where they share the contractor config.

---

## 5. Resolved Decisions (formerly Open Questions)

- **OQ-A → RESOLVED (2026-06-01):** Drafter **stays `GEMINI_FLASH_LITE`** (cheapest stable,
  $0.075/$0.30). No move to Haiku. (REQ-PCMR-101.)
- **OQ-B → RESOLVED (2026-06-01):** Opus 4.8 lead+reviewer confirmed; **cost increase
  acknowledged**. Ships with a documented opt-down (`lead_agent=Models.CLAUDE_SONNET_LATEST`) in
  the workflow guide — **no config toggle** (NR-1). (REQ-PCMR-100/120.)
- **OQ-C (preview models):** `gemini-3-flash-preview` / `gemini-3.1-pro-preview` remain
  **excluded** from contractor defaults, per catalog preview-only policy. (Assumed; flag if
  this should change.)

---

## 6. Affected Code (from inspection)

| Area | File / anchor | Change shape | Requirements |
|------|---------------|--------------|--------------|
| Lead/drafter defaults | `model_catalog.py:132-133` | `PRIMARY_CONTRACTOR_LEAD` → `CLAUDE_OPUS_LATEST`; drafter stays catalog constant | REQ-PCMR-100/101 |
| Dead enum | `primary_contractor_models.py:36-50` | delete `DrafterChoice` (or catalog-derive) | REQ-PCMR-110 |
| Contextcore variants | `primary_contractor_contextcore_workflow.py:30,259` | drop `gpt-4o-mini`; default via config | REQ-PCMR-111 |
| Integration adapter | `integrations/contextcore.py:390` | drop `gpt-4o-mini` literal in example/default | REQ-PCMR-111 |
| TUI config defaults | `config.py:71-78` | derive from catalog | REQ-PCMR-112 |
| Docstrings | `primary_contractor_workflow.py:~195-215` (+ siblings) | refresh recommended lists | REQ-PCMR-120 |
| Regression test | new `tests/unit/test_contractor_model_centralization.py` | assert all defaults catalog-backed | REQ-PCMR-102/130 |

---

*v0.1 — initial draft from codebase inspection. Decisions: Opus-4.8 lead, route-through-catalog
only, all contractor touchpoints. 3 open questions (drafter cheap-model choice, Opus cost
opt-down, preview exclusion) pending confirmation.*
