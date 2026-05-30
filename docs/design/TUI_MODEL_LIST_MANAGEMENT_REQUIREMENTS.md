# TUI Model-List Management Requirements

**Version:** 0.3 (Post-CRP — R1 suggestions triaged & applied)
**Date:** 2026-05-28
**Status:** Draft (pre-implementation)
**Prefix:** REQ-TMM (TUI Model Management)

---

## 0. Planning & Review Insights

### 0.1 Self-reflective planning pass (v0.1 → v0.2)

> The planning pass invalidated or reshaped most of the original requirements —
> the "add models via the TUI" capability is **largely already built**, just
> incomplete and fragmented.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| There is one hardcoded model list to fix | There are **four** model-list sources, unsynchronized (see §1) | Reframed from "make the list editable" to "manage + reconcile across sources" |
| The TUI can't add models at all | `ModelDiscoveryService` already queries provider APIs and **persists** to `~/.startd8/discovered_models.json` (24h cache); a "Discover Models" menu action already exists (`tui_improved.py:~2020`) | ADD-via-discovery is **done** — narrow the requirement to manual add + edit + remove |
| Users can't enter a model not in the list | The agent-config flow already has an **"Enter custom model name"** option (`tui_improved.py:2174`) | One-off custom entry exists; gap is *persisting* it to a reusable list |
| An unknown model id will be rejected | Provider validation **warns, does not reject** (`anthropic.py:250-252`) | A custom model already "works" at create time — the user's actual wall was the `framework` AttributeError, now fixed, not list membership |
| Updating `AGENT_TYPES` + `model_catalog` makes a model fully usable | `<Provider>.HARDCODED_MODELS` is a **third** source; `model_catalog` is a **fourth** (tier routing only) | A model added in one source is invisible to the others — reconciliation is the core problem |

### 0.2 CRP Round 1 triage (v0.2 → v0.3)

> A dual-document Convergent Review (reviewer attribution: `claude-opus-4-8`)
> produced 10 requirements suggestions (R1-F1…F10). All 10 were **ACCEPTED**;
> F2 and F9 were accepted in trimmed form. Companion plan suggestions (R1-S1…S9)
> were triaged in the plan doc.

| CRP id | Disposition | Where applied |
|--------|-------------|---------------|
| R1-F1 (provider-scope contradiction) | ACCEPT | REQ-TMM-100/110 scoped; NR-7 added |
| R1-F2 (testable acceptance criteria) | ACCEPT (trimmed: concise **AC** lines, not full Given/When/Then) | every REQ-TMM-1xx |
| R1-F3 (resolve OQ-A) | ACCEPT | REQ-TMM-104 fixes the path; OQ-A closed |
| R1-F4 (define `user_models.json` schema) | ACCEPT | new REQ-TMM-105 |
| R1-F5 (dedup tie-break + metadata authority) | ACCEPT | REQ-TMM-131 |
| R1-F6 (corrupt/unwritable file behavior) | ACCEPT | new REQ-TMM-106 |
| R1-F7 (edit-collision behavior) | ACCEPT | REQ-TMM-103 |
| R1-F8 (constrain `model_id` input) | ACCEPT | new REQ-TMM-107 |
| R1-F9 (objective "unrecognized") | ACCEPT (trimmed: define four-source check now; fuzzy-match *suggest* deferred to v2) | REQ-TMM-120 |
| R1-F10 (`get_latest_model` won't auto-select overlay) | ACCEPT | REQ-TMM-130 + NR-6 |

**Resolved open questions (all closed in v0.3):**
- **OQ-A → Global.** Overlay lives at `~/.startd8/user_models.json`, matching `custom_agents.json` and `discovered_models.json` defaults (REQ-TMM-104).
- **OQ-B → `tier` required, `capabilities` defaulted.** User-added models require `tier`; `capabilities` defaults to `{"text","code"}` when unspecified (REQ-TMM-105).
- **OQ-C → Suppression supported, with resurrection.** Removing a *baseline/discovered* id records a suppression; re-adding the same id clears it (REQ-TMM-102).

### 0.3 Added beyond CRP (flagged for review)

- **REQ-TMM-132** — eliminate the #2/#4 hardcoded-list duplication (`AGENT_TYPES['models']` should derive from the provider). This is the concrete fix for the duplication that motivated the whole effort; it was discussed with the user but is **not** a CRP suggestion. **Veto candidate** if scope should stay overlay-only.

---

## 1. Problem Statement

A user tried to configure a newer Opus model in the TUI and hit a wall. Two
distinct issues were tangled together:

1. **A crash** — `CustomAgentManager` had no `framework` attribute (fixed separately).
2. **A fragmented, partly-hardcoded model catalog** — adding/curating model
   identifiers requires editing source in up to four places, and the TUI only
   exposes one of the four mechanisms for changing the list (API discovery).

### The four model-list sources today

| # | Source | File | Used for | TUI-editable today? |
|---|--------|------|----------|---------------------|
| 1 | `_MODEL_REGISTRY` + `Models` constants | `model_catalog.py` | Tier routing, escalation, SDK-internal defaults | No (source only) |
| 2 | `<Provider>.HARDCODED_MODELS` | `providers/{anthropic,openai,gemini}.py` | Provider baseline / `supported_models` | No (source only) |
| 3 | `discovered_models.json` (via `ModelDiscoveryService`) | `~/.startd8/` | Merged into `supported_models`; shown in agent picker | **Partially** — API discovery only (no manual add/edit/remove) |
| 4 | `AGENT_TYPES[type]['models']` | `tui_improved.py` | TUI agent-config picker baseline | No (source only) |

The TUI agent picker shows **#4 ∪ #2 ∪ #3** (merged) for the `claude` and `gpt4`
agent types only. It does **not** consult #1, and there is no `gemini` agent type
(Gemini discovery runs but is never surfaced in the picker). Manual one-off entry
exists but is not saved. Net gap: **no manual, persistent, TUI-driven CRUD over
the model list, and no reconciliation across sources.**

---

## 2. Requirements

> **Acceptance Criteria (AC)** are intentionally compact and testable. Unless
> noted, "user list" = the persistent overlay at `~/.startd8/user_models.json`.

### 2.1 Manual model-list CRUD (the core gap)

- **REQ-TMM-100** — The TUI MUST provide a "Manage Models" action that lists all model ids visible for a chosen provider, annotated by origin (`baseline` / `discovered` / `user-added`). **Scope:** the provider chooser MUST offer `anthropic`, `openai`, and `gemini` (the providers with discovery + a `HARDCODED_MODELS` baseline), independent of whether each has an agent type in the picker.
  - **AC:** For each of the three providers, the action renders a list where every id carries exactly one origin label.
- **REQ-TMM-101** — The TUI MUST let a user **add** a model id to the user list for a provider without editing source.
  - **AC:** After add + reopen, the id appears with origin `user-added` and persists across process restarts.
- **REQ-TMM-102** — The TUI MUST let a user **remove** a `user-added` model from the user list. Removing a `baseline`/`discovered` id MUST record a **suppression** (hide-only; baseline/discovered sources are never mutated, per NR-1). Re-adding a suppressed id (REQ-TMM-101) MUST clear its suppression (resurrection).
  - **AC:** Remove of a user id deletes the record; remove of a baseline id hides it from the merged view but leaves the source intact; subsequent add of that id un-hides it.
- **REQ-TMM-103** — The TUI MUST let a user **edit** a `user-added` model's id and `tier` (and optionally `capabilities`). Editing an id to one that **already exists** in any source (user/baseline/discovered) MUST be **rejected** with a message; no overwrite or silent merge.
  - **AC:** Edit to a free id succeeds; edit to a colliding id returns a defined error and leaves state unchanged.
- **REQ-TMM-104** — User-added models MUST persist in `~/.startd8/user_models.json` — a **dedicated, global** file separate from `discovered_models.json`, so the 24h discovery refresh never overwrites manual entries. (OQ-A resolved: global, matching existing `.startd8` conventions.)
  - **AC:** Discovery refresh leaves `user_models.json` byte-untouched; manual edits survive a discovery run.
- **REQ-TMM-105** — The `user_models.json` schema MUST be explicitly versioned and typed (R1-F4). A user-model record MUST carry `model_id` (str), `tier` (str, required — OQ-B), `capabilities` (list[str], default `["text","code"]`), and provenance (`added_at`, `source ∈ {"manual","custom-entry"}`). Canonical shape:
  ```json
  {
    "version": 1,
    "last_updated": "<iso8601>",
    "models": {
      "<provider>": [
        {"model_id": "…", "tier": "flagship",
         "capabilities": ["text","code"],
         "added_at": "<iso8601>", "source": "manual"}
      ]
    },
    "suppressed": {"<provider>": ["<model_id>", …]}
  }
  ```
  - **AC:** A round-trip (write → read) preserves all fields; a v1 file loads under the reader; `tier` MUST validate against `{flagship, balanced, fast, mini, reasoning}` and an invalid record is dropped with a warning (see REQ-TMM-130).
- **REQ-TMM-106** — A missing, unreadable, malformed, or unwritable `user_models.json` MUST degrade gracefully: log a warning and fall back to an **empty overlay**; the TUI MUST NOT crash. (Consistent with `model_discovery.py:50,63` warn-and-continue.) (R1-F6)
  - **AC:** Malformed JSON → empty overlay + logged warning, no exception; unwritable path on save → warning, in-memory state preserved.
- **REQ-TMM-107** — On add/edit/custom-entry, a `model_id` MUST be normalized and constrained before persistence or rendering: trimmed, non-empty, max length 200, and rejecting newlines / control chars and the provider-separator `:` (which would corrupt `provider:model` specs and `questionary` choice lists). (R1-F8)
  - **AC:** An id containing `\n`, a control char, or `:` is rejected (or normalized) and never written to disk or shown as a choice.

### 2.2 Surfacing in the agent-config picker

- **REQ-TMM-110** — For providers that have a builtin agent type (v1: `anthropic`→`claude`, `openai`→`gpt4`), the agent-config model picker (`_configure_builtin_agent`) MUST include `user-added` models under a clear `─── Your Models ───` separator, alongside the existing "Discovered Models" group. (Gemini has no agent type in v1 — see NR-7.)
  - **AC:** With a user-added Claude model present, it appears in the `claude` picker under the Your Models separator.
- **REQ-TMM-111** — When a user enters a model via the existing "Enter custom model name" path, the TUI MUST offer to persist it to the user list (REQ-TMM-101/105), turning one-off entry into a reusable entry, with `source: "custom-entry"`. Persistence MUST apply REQ-TMM-107 normalization.
  - **AC:** Accepting the "Save to your model list?" prompt yields a `user-added` record on next open; declining uses the model for that agent only.

### 2.3 Validation (informational, non-blocking)

- **REQ-TMM-120** — A pure helper `classify_model_id(provider, model_id)` MUST cross-check all four sources and return exactly one of `known` (in #1/#2/#3), `user` (in the overlay), or `unrecognized` (in none). On add/custom-entry of an `unrecognized` id, the TUI MUST show a confirm prompt ("not found in any known source — add anyway?"). Fuzzy near-miss/typo *suggestions* are deferred to v2 (R1-F9, trimmed).
  - **AC:** `classify_model_id` returns `unrecognized` **iff** the id is absent from all four sources; the confirm prompt defaults to proceed.
- **REQ-TMM-121** — Validation MUST NOT block agent creation for unknown models (consistent with the provider warn-don't-reject behavior, `anthropic.py:247-254`).
  - **AC:** Creating an agent with an `unrecognized` model succeeds after the user confirms.

### 2.4 Reconciliation across sources

- **REQ-TMM-130** — A user-added model with a valid `tier` MUST be discoverable by the `model_catalog` lookup consumers — `get_model_info`, `is_known_model`, `list_models_by_tier`, `list_models_by_capability`, and `get_escalation_target` — via an overlay over `_MODEL_REGISTRY`. **Limitation (NR-6):** `get_latest_model` is tier→constant keyed and will **not** auto-select overlay models in v1; routing *visibility* ≠ tier-default *selection* (R1-F10). Records with an invalid `tier` MUST be excluded from the overlay (REQ-TMM-105) so routing never trusts a bad tier.
  - **AC:** An overlay model is returned by `get_model_info`/`is_known_model`; `get_escalation_target` honors its tier; `get_latest_model` does **not** return it as a default.
- **REQ-TMM-131** — The merged, user-visible model list MUST be de-duplicated across all sources into a single record per id. On collision, precedence is **user-added > discovered > baseline**, and the winning origin is authoritative for **both** the origin label **and** the metadata (`tier`/`capabilities`) used downstream (R1-F5).
  - **AC:** An id present in all three sources resolves to origin `user-added` and the user record's `tier`.

### 2.5 Duplication elimination (flagged — see §0.3)

- **REQ-TMM-132** — `AGENT_TYPES[type]['models']` MUST NOT maintain a parallel hardcoded model list; the TUI picker MUST derive its baseline from `provider.supported_models` (which already merges `HARDCODED_MODELS` ∪ discovered), leaving exactly one curated baseline per provider (#2). `default_model` and non-model metadata in `AGENT_TYPES` are retained.
  - **AC:** Removing a model from `HARDCODED_MODELS` removes it from the picker without any `AGENT_TYPES` edit; adding to `HARDCODED_MODELS` surfaces it in the picker automatically.

---

## 3. Non-Requirements

- **NR-1** — Will NOT make `<Provider>.HARDCODED_MODELS`, `AGENT_TYPES`, or `_MODEL_REGISTRY` source lists editable from the TUI. These remain the curated baseline; the overlay file is the user-editable layer.
- **NR-2** — Will NOT enforce an allowlist that rejects unknown models at agent-creation time.
- **NR-3** — Will NOT add pricing/cost metadata for user-added models in v1 (cost tracking falls back to defaults; out of scope).
- **NR-4** — Will NOT auto-sync user-added models back upstream into source files or upstream provider catalogs.
- **NR-5** — Will NOT change the existing API-driven discovery behavior (#3) beyond adding the separate manual layer.
- **NR-6** — Will NOT make `get_latest_model` auto-select overlay models in v1 (overlay models are resolvable but never returned as a tier default). (From R1-F10.)
- **NR-7** — Will NOT add a `gemini` agent type to the picker in v1. Gemini is manageable via REQ-TMM-100 (overlay is provider-keyed) but not surfaced in `_configure_builtin_agent`. (From R1-F1.)

---

## 4. Resolved Decisions (formerly Open Questions)

- **OQ-A → Resolved (REQ-TMM-104):** Overlay is **global** at `~/.startd8/user_models.json`.
- **OQ-B → Resolved (REQ-TMM-105):** `tier` is **required**; `capabilities` defaults to `["text","code"]`.
- **OQ-C → Resolved (REQ-TMM-102):** Baseline removal is a **suppression** (hide-only) with **resurrection** on re-add.

No open questions remain for v1.

---

## 5. Affected Code (from planning pass)

| Area | File / anchor | Change shape | Requirements |
|------|---------------|--------------|--------------|
| Manual CRUD store | new `user_models.py` (reuse `model_discovery.py` file-store mechanics) | Load/save/recover `user_models.json`, CRUD, merge, overlay export | REQ-TMM-101…107, 131 |
| Catalog overlay | `model_catalog.py` (`get_model_info`, `is_known_model`, `list_models_by_*`, `get_escalation_target`) | Read overlay as a layer over `_MODEL_REGISTRY`; tier validation | REQ-TMM-130, 131 |
| Four-source classifier | new `classify_model_id()` helper | Single origin/dedup spine for picker, manage-list, validation | REQ-TMM-120, 131 |
| TUI "Manage Models" menu | `tui_improved.py` (near discover flow `~1994-2104`) | New action + add/edit/remove/suppress prompts | REQ-TMM-100…103 |
| Agent-config picker | `tui_improved.py:2130-2188` | Your-Models group; persist-on-custom-entry; **derive from provider (132)** | REQ-TMM-110, 111, 132 |
| Unknown-model flag | `tui_improved.py` add/entry paths | Cross-check via `classify_model_id` before confirm | REQ-TMM-120 |

---

*v0.3 — CRP R1 applied. 10/10 requirements suggestions accepted (F2, F9 trimmed),
3 open questions resolved, 4 new requirements added (105/106/107/132), 2 new
non-requirements (NR-6/7). REQ-TMM-132 is flagged as a non-CRP addition for veto.*
