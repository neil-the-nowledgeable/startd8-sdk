# TUI Model-List Management — Implementation Plan

**Version:** 0.2 (CRP R1 plan-suggestions grafted; aligned to requirements v0.3)
**Date:** 2026-05-28
**Status:** Draft (pre-implementation)
**Requirements prefix:** REQ-TMM
**Plan prefix:** PL-TMM

> This plan operationalizes the post-CRP requirements. The key insight from the
> requirements' self-reflective pass is that ADD-via-discovery is already built;
> the real work is a **manual, persistent, user-owned overlay** plus
> **reconciliation across the four existing model-list sources**. This plan is
> scoped to that overlay layer and deliberately does not touch the curated
> baseline sources (NR-1), with one flagged exception (REQ-TMM-132).

---

## 0. Changelog — CRP R1 graft (v0.1 → v0.2)

All 9 plan suggestions (R1-S1…S9) were ACCEPTED and grafted; the S-appendix was
removed. Requirements v0.3 changes (REQ-TMM-105/106/107/132, resolved OQs) are
reflected throughout.

| CRP id | Disposition | Grafted into |
|--------|-------------|--------------|
| R1-S1 (reuse `ModelDiscoveryService` file-store) | ACCEPT | §3.1 (shared `_JsonFileStore` base) |
| R1-S2 (single `classify_model_id`/`merge_view` spine) | ACCEPT | §3.6, §3.1 `merge_view` |
| R1-S3 (tier boundary validator before routing) | ACCEPT | §3.2, §3.3, PL-TMM-2 |
| R1-S4 (atomic write-rename + reload-before-write) | ACCEPT | §3.1 store contract |
| R1-S5 (state v1 provider set; handle missing gemini type) | ACCEPT | §3.4/§3.5, §6 (reqs NR-7) |
| R1-S6 (provenance/audit field per user model) | ACCEPT | §3.2 schema |
| R1-S7 (suppression resurrection lifecycle) | ACCEPT | §3.2/§3.4 (req REQ-TMM-102) |
| R1-S8 (normalize/validate `model_id` on ingress) | ACCEPT | §3.5/§3.6 (req REQ-TMM-107) |
| R1-S9 (migration test for `version` key) | ACCEPT | §5 testing |

---

## 1. Goal & Scope

Deliver TUI-driven, persistent CRUD over a user-owned model list that:

1. Persists to a dedicated global file separate from `discovered_models.json` (REQ-TMM-104).
2. Surfaces in the agent-config picker alongside discovered models (REQ-TMM-110/111).
3. Is visible to `model_catalog` lookup consumers via an overlay (REQ-TMM-130).
4. Produces a single, de-duplicated, origin-annotated view across all four sources (REQ-TMM-131).
5. Flags unrecognized ids informationally without blocking agent creation (REQ-TMM-120/121).
6. (Flagged — REQ-TMM-132) Removes the `AGENT_TYPES`/`HARDCODED_MODELS` duplication by deriving the picker baseline from the provider.

Out of scope: editing baseline source lists, allowlist enforcement, pricing
metadata, upstream sync, `get_latest_model` overlay auto-select, a `gemini` agent
type (NR-1 through NR-7).

## 2. Current-State Anchors (verified during planning)

| Concern | Code anchor | Behavior today |
|---------|-------------|----------------|
| Discovery persistence | `model_discovery.py:ModelDiscoveryService` | Writes `~/.startd8/discovered_models.json`, 24h cache, `_load`/`_save` with `JSONDecodeError`/`IOError` recovery (`:40-64`), `merge_models()` helper |
| Provider merge | `providers/anthropic.py:_get_models` (`merge_models('anthropic', HARDCODED_MODELS)`) | `supported_models` = HARDCODED ∪ discovered |
| Picker merge | `tui_improved.py:_configure_builtin_agent` (~2130-2188) | Merges `AGENT_TYPES[type]['models']` ∪ `provider.supported_models`; only for `claude` and `gpt4` agent types |
| Custom one-off entry | `tui_improved.py:2174-2188` | "Enter custom model name" — used immediately, never persisted |
| Permissive validation | `providers/anthropic.py:247-254` | Warns (does not reject) on unknown model at `create_agent` |
| Catalog metadata | `model_catalog.py:_MODEL_REGISTRY`, `get_model_info`, `is_known_model`, `get_latest_model`, `get_escalation_target` | Tier/capabilities drive routing + escalation; `get_latest_model` is tier→constant keyed (does NOT read `_MODEL_REGISTRY`) |
| Discover menu | `tui_improved.py:~2018-2104` | "Discover Models" action invokes `discover_all_models()` |

**Note:** `CustomAgentManager.AGENT_TYPES` contains only `claude`, `gpt4`,
`openai_compatible`, `mock`. Gemini discovery runs but is **not** surfaced in the
builtin agent picker (no `gemini` agent type). v1 picker scope is therefore
`anthropic`→`claude` and `openai`→`gpt4` (REQ-TMM-110, NR-7); the Manage-Models
action still covers all three discovered providers (REQ-TMM-100).

## 3. Architecture

### 3.1 Shared file-store + new module `user_models.py` (R1-S1, R1-S4)

To avoid re-hand-rolling persistence (Mottainai), **extract** the load/save/cache/
recovery mechanics currently inline in `ModelDiscoveryService` (`model_discovery.py:40-64`)
into a small reusable helper — `_JsonFileStore` (load, atomic save, malformed-file
recovery) — and have **both** `ModelDiscoveryService` and the new store use it.
This guarantees identical corruption behavior (REQ-TMM-106).

`UserModelStore(config_dir: Optional[Path] = None)` built on `_JsonFileStore`:

- `add(provider, model_id, *, tier, capabilities=None, source="manual")` → idempotent upsert; normalizes id (REQ-TMM-107); clears any suppression for that id (REQ-TMM-102 resurrection).
- `remove(provider, model_id)` → deletes a user entry; if the id is baseline/discovered, records a suppression instead (REQ-TMM-102).
- `edit(provider, model_id, *, new_id=None, tier=None, capabilities=None)` → rejects `new_id` that collides with any source (REQ-TMM-103).
- `list(provider)` → user entries with metadata.
- `merge_view(provider, baseline, discovered)` → single de-duplicated, origin-annotated list (REQ-TMM-131); built on `classify_model_id` (§3.6, R1-S2).
- `as_catalog_overlay()` → validated `ModelInfo` dict for `model_catalog` (REQ-TMM-130).

**Persistence contract (R1-S4):** writes go to a temp file + `os.replace` (atomic
rename); each mutation does **reload-before-write** to merge concurrent edits from
a second TUI session.

### 3.2 File schema (`user_models.json`) (R1-S6, R1-S9; REQ-TMM-105)

```json
{
  "version": 1,
  "last_updated": "2026-05-28T17:50:00Z",
  "models": {
    "anthropic": [
      {"model_id": "claude-opus-4-7", "tier": "flagship",
       "capabilities": ["text", "code"], "added_at": "2026-05-28T17:50:00Z",
       "source": "manual"}
    ]
  },
  "suppressed": { "anthropic": [] }
}
```

- `version` enables forward-compatible migration; a v1→v2 reader path is exercised by a test (R1-S9), not left decorative.
- `source ∈ {"manual","custom-entry"}` + `added_at` provide provenance for the manage-list view (R1-S6) — data already in hand at add-time.
- `suppressed` backs hide-only removal (REQ-TMM-102) without mutating baseline sources.
- `tier` is required and validated against `{flagship,balanced,fast,mini,reasoning}` (R1-S3); `capabilities` defaults to `["text","code"]`.

### 3.3 `model_catalog` overlay (REQ-TMM-130, R1-S3)

- Add `_load_user_overlay()` that reads `user_models.json` once and builds `ModelInfo` entries (provider/model_id/tier/capabilities).
- **Boundary validation (R1-S3):** an overlay record whose `tier` is not a known tier is **dropped with a warning** before it reaches routing — invalid tier must never silently disable `get_escalation_target` (which returns `None` on unknown tier).
- `get_model_info`, `is_known_model`, `list_models_by_tier`, `list_models_by_capability`, and `get_escalation_target` consult the overlay **after** `_MODEL_REGISTRY` (user-added > baseline precedence per REQ-TMM-131).
- `get_latest_model` is tier→constant keyed and does **not** read the registry; overlay models can be *resolved* but will not be *selected* as a tier default (NR-6 — documented limitation, see Risks).

### 3.4 TUI "Manage Models" menu (REQ-TMM-100/101/102/103)

- New action near the discover-models flow (`tui_improved.py` ~1994-2104).
- Provider chooser offers **anthropic / openai / gemini** (all three have discovery + a baseline), independent of picker agent types (REQ-TMM-100, R1-S5).
- List view annotated by origin (`baseline` / `discovered` / `user-added`) using `merge_view`, plus provenance (`source`, `added_at`) for user entries (R1-S6).
- Sub-actions: Add / Edit (user-added only) / Remove (user-added delete; baseline/discovered → suppress, with resurrection on re-add — R1-S7).
- Reuses `questionary` + Rich `Table` patterns already in the discover flow.

### 3.5 Agent-config picker integration (REQ-TMM-110/111/132)

- v1 picker scope: `claude` (anthropic) and `gpt4` (openai); Gemini excluded (NR-7, R1-S5).
- **REQ-TMM-132 (flagged):** replace `all_models = list(type_info['models'])` so the baseline derives from `provider.supported_models` (= `HARDCODED_MODELS` ∪ discovered) instead of the parallel `AGENT_TYPES['models']` copy. `default_model`/other `AGENT_TYPES` metadata is retained. If 132 is vetoed, the picker keeps reading `AGENT_TYPES['models']` and the rest of this plan is unaffected.
- After merging discovered models, append a `─── Your Models ───` separator group from `UserModelStore.list(provider)`.
- After the "Enter custom model name" path resolves a value, normalize it (REQ-TMM-107) then prompt "Save to your model list?" → on yes, `UserModelStore.add(..., source="custom-entry")` (REQ-TMM-111), prompting for `tier`.

### 3.6 Informational validation + the shared spine (REQ-TMM-120/121, R1-S2, R1-S8)

- A pure helper `classify_model_id(provider, model_id)` cross-checks all four sources (`_MODEL_REGISTRY`, `HARDCODED_MODELS`, discovered, user) and returns `known | user | unrecognized`.
- **This helper is the single spine (R1-S2)** consumed by §3.4 origin annotation, §3.1 `merge_view` dedup, and this validation — built once, used three times.
- On add/custom-entry: first normalize/validate input (REQ-TMM-107, R1-S8 — reject newlines/control chars/`:`, max len 200); if `classify` returns `unrecognized`, show a confirm prompt that defaults to proceed (non-blocking, REQ-TMM-121). Fuzzy typo *suggestions* are deferred to v2 (REQ-TMM-120).

## 4. Implementation Sequence

| Step | Deliverable | Requirements |
|------|-------------|--------------|
| PL-TMM-1 | Extract `_JsonFileStore`; refactor `ModelDiscoveryService` onto it (no behavior change) | REQ-TMM-106 (foundation, R1-S1) |
| PL-TMM-2 | `user_models.py` store (CRUD, suppression+resurrection, atomic/reload writes, normalization) + schema + unit tests | REQ-TMM-101/102/103/104/105/106/107 |
| PL-TMM-3 | `classify_model_id` four-source validator (the shared spine) | REQ-TMM-120/121 (R1-S2) |
| PL-TMM-4 | `model_catalog` overlay reader + tier boundary validation + precedence/dedup | REQ-TMM-130/131 (R1-S3) |
| PL-TMM-5 | TUI "Manage Models" menu (list/add/edit/remove/suppress) over all 3 providers | REQ-TMM-100/101/102/103 |
| PL-TMM-6 | Picker integration: Your-Models group + persist-on-custom-entry | REQ-TMM-110/111 |
| PL-TMM-7 | (Flagged) Picker baseline derives from `provider.supported_models` | REQ-TMM-132 |

> Ordering rationale: PL-TMM-1 is a no-behavior-change refactor that both stores
> depend on; PL-TMM-3's classifier is a dependency of PL-TMM-4's dedup and
> PL-TMM-5/6's UI. PL-TMM-7 is isolated and last so a veto drops it cleanly.

## 5. Testing Strategy

- **Unit — `_JsonFileStore`:** both stores recover identically from a malformed file (R1-S1); atomic write leaves no partial file on simulated crash.
- **Unit — `UserModelStore`:** CRUD round-trips; suppression + resurrection (R1-S7); edit-collision rejection (REQ-TMM-103); `model_id` normalization rejects newline/`:`/control chars (R1-S8); interleaved `add()` from two instances preserves both entries (R1-S4); **`version` migration test** — a v1 file loads under a v2-aware reader (R1-S9).
- **Unit — `model_catalog` overlay:** overlay model resolves via `get_model_info`; precedence over a colliding baseline id (REQ-TMM-131); escalation honors overlay tier; **invalid-tier record is dropped with warning and escalation still works for valid ones** (R1-S3); `get_latest_model` does NOT return an overlay model (NR-6).
- **Unit — `classify_model_id`:** returns the correct class for an id in each of the four sources and `unrecognized` only when absent from all four (REQ-TMM-120).
- **TUI — light integration:** `questionary` monkeypatched (existing pattern, e.g. `tests/unit/test_nim_entry_paths.py`-style). Manage-Models list renders origin labels for each provider; picker shows the Your-Models group for claude/gpt4; persist-on-custom-entry round-trips.
- **(PL-TMM-7)** picker derivation: removing a model from `HARDCODED_MODELS` removes it from the picker without an `AGENT_TYPES` edit (REQ-TMM-132 AC).

## 6. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| `get_latest_model` ignores overlay → TUI-added flagship never auto-selected | Documented v1 limitation (NR-6); overlay covers `get_model_info`/`is_known_model`/escalation lookups |
| Gemini has no `claude`/`gpt4`-style agent type | v1 picker scope = anthropic+openai (NR-7); Manage-Models still covers gemini (REQ-TMM-100) |
| Concurrent writes from two TUI sessions | Atomic temp-file + `os.replace` and reload-before-write (R1-S4, §3.1) |
| `_MODEL_REGISTRY` is a `frozen` dataclass dict | Overlay is a separate dict layer, not a mutation (§3.3) |
| Invalid user `tier` silently disables escalation | Boundary validator drops bad-tier records with a warning before routing (R1-S3, §3.3) |
| Extracting `_JsonFileStore` regresses discovery | PL-TMM-1 is no-behavior-change; existing discovery tests must stay green before proceeding |
| REQ-TMM-132 changes picker baseline source | Isolated as last step (PL-TMM-7); vetoable without affecting PL-TMM-1..6 |

## 7. Out of Scope (mirrors Non-Requirements)

NR-1 baseline edits, NR-2 allowlist rejection, NR-3 pricing, NR-4 upstream sync,
NR-5 discovery-behavior changes, NR-6 `get_latest_model` overlay auto-select,
NR-7 `gemini` agent type.

---

## Requirements Coverage Matrix

> Updated after CRP R1 graft. Maps each REQ-TMM requirement to plan coverage.

| Requirement | Plan Step(s) / Section | Coverage | Notes |
|-------------|------------------------|----------|-------|
| REQ-TMM-100 (Manage Models action, origin-annotated, 3 providers) | §3.4, PL-TMM-5 | Full | Provider scope resolved; origin via shared `classify_model_id` (R1-S2). |
| REQ-TMM-101 (add to persistent user list) | §3.1 `add`, §3.4, PL-TMM-2/5 | Full | — |
| REQ-TMM-102 (remove user; suppress baseline + resurrection) | §3.1 `remove`, §3.2 `suppressed`, PL-TMM-2/5 | Full | Lifecycle resolved (R1-S7). |
| REQ-TMM-103 (edit id + tier; collision → reject) | §3.1 `edit`, §3.4, PL-TMM-2/5 | Full | Collision rule defined (R1-F7). |
| REQ-TMM-104 (persist to dedicated global file) | §3.1, §3.2, PL-TMM-2 | Full | Path fixed global (OQ-A). |
| REQ-TMM-105 (versioned, typed schema) | §3.2, PL-TMM-2 | Full | Provenance (R1-S6) + migration test (R1-S9). |
| REQ-TMM-106 (corrupt/unwritable → warn, empty, no crash) | §3.1 `_JsonFileStore`, PL-TMM-1 | Full | Shared recovery (R1-S1). |
| REQ-TMM-107 (model_id input constraints) | §3.6, PL-TMM-2/3 | Full | Normalization (R1-S8). |
| REQ-TMM-110 (picker Your-Models group, claude/gpt4) | §3.5, PL-TMM-6 | Full | Provider scope resolved (NR-7, R1-S5). |
| REQ-TMM-111 (persist one-off custom entry) | §3.5, PL-TMM-6 | Full | Normalized before persist (R1-S8). |
| REQ-TMM-120 (flag unrecognized w/ confirm) | §3.6 `classify_model_id`, PL-TMM-3 | Full | Objective four-source check; fuzzy suggest deferred to v2. |
| REQ-TMM-121 (non-blocking validation) | §3.6, PL-TMM-3 | Full | — |
| REQ-TMM-130 (overlay visible to model_catalog lookups) | §3.3, PL-TMM-4 | Full | Tier validation (R1-S3); `get_latest_model` excluded (NR-6, R1-F10). |
| REQ-TMM-131 (dedup, single annotated origin + metadata authority) | §3.1 `merge_view`, §3.3, PL-TMM-3/4 | Full | Metadata authority resolved (R1-F5). |
| REQ-TMM-132 (picker derives from provider — flagged) | §3.5, PL-TMM-7 | Full (vetoable) | Isolated last step. |
