# Requirements — JavaScript host / multi-framework layering and Vue support

**Version:** 0.2 (Post-planning — self-reflective update)  
**Status:** Draft  
**Audience:** Prime Contractor, MicroPrime, language registry, plan-ingestion  
**Goal:** Introduce a **JavaScript host abstraction** where today’s **Node.js plain-source** profile is the **first of n+1** framework dialects (Node-style modules, Vue SFCs, future frameworks), then ship **basic Vue** support and define **full parity** with current Node.js capabilities.

---

## 0. Planning insights (self-reflective update v0.1 → v0.2)

This section records what **implementation planning (Phases A–C)** and a **read of the current codebase** showed about the earlier draft. The intent is to **cut accidental complexity** before coding: fewer parallel concepts, reuse what already exists, and **one** place to extend when adding `vue`.

### 0.1 Discoveries (requirements ↔ code/planning)

| v0.1 assumption | Planning / code discovery | Requirement or plan impact |
|-----------------|---------------------------|------------------------------|
| REQ-JSF-007 needs new forward-manifest fields | **`ForwardFileSpec` already has `language: Optional[str]`** (`forward_manifest.py`, FR-DFA-009); plan-ingestion already builds specs with optional language. | **Prefer `language` override first**; add new fields only if `language` cannot encode dialect (e.g. need `vue_sfc` vs `vue` — then still prefer extending allowed values for `language`, not parallel hint keys). |
| MicroPrime needs a new `get_parser_id` API immediately | Engine and call sites already thread **`LanguageProfile`** and **`ForwardFileSpec`** in many paths. | **Phase A default:** pass **profile** (and existing `language_id`) into routing; add `parser_kind` / `get_parser_id` **only** when one `language_id` truly needs multiple parsers. Avoid two parallel routing dimensions on day one. |
| `javascript_host.py` is required in Phase A | Node profile is self-contained today; risk of **empty indirection** if extracted too early. | **Tier host extraction:** Phase A MAY start with **shared constants / helpers colocated** on `NodeLanguageProfile` + `VueLanguageProfile` importing the same tuple/strings; **promote** to `javascript_host.py` only when duplication is real (second dialect landed). |
| Vue extraction + splice are separate concerns everywhere | Plans split B.2/B.3 heavily. | **Single module boundary** for SFC: **extract + re-inject** in one place (e.g. `languages/vue_sfc.py`) so MicroPrime does not scatter string surgery. |
| `resolve_language` is the only choke point | **`detect_language`** (`micro_prime/lang_detect.py`) uses a **closed `Language` Literal** that omits `vue`; extension branch already delegates to **`LanguageRegistry.get_extension_map()`**. | On `vue` registration: **widen or replace Literal with `str`**, or derive MicroPrime’s language string from **`profile.language_id`** after resolve — avoid a third naming scheme. **REQ-JSF-006** amended: dominant resolution + **consistency** with `detect_language` / `ForwardFileSpec.language`. |
| `_language_id_from_path` in `engine.py` defaults unknown → `python` | Same risk as `.vue` today for any new ext. | Part A/B: when tightening repair/splice validation, **prefer calling `LanguageRegistry` / profile** instead of growing `_language_id_from_path` special cases (document as **tech-debt opportunistic fix** alongside Vue). |
| Part C needs every bell on day one | Several P-* items are P2/P3. | Plans already stream C.5/C.6; REQ text unchanged but **acceptance order** clarified: P-011 / P-012 / P-013 may ship **after** P-002–P-010 **without** blocking “parity core” milestone. |

### 0.2 Resolved open questions

| ID | Resolution |
|----|------------|
| **OQ-1** Where do dialect hints live? | **`ForwardFileSpec.language`** first; document values `nodejs`, `vue`, etc., aligned with `language_id`. |
| **OQ-2** Host module file vs inline? | **Defer file split** until duplication justifies it (§0.1 table). |
| **OQ-3** Parser routing API shape? | **`LanguageProfile`-driven** first; optional `parser_kind` later if needed. |

### 0.3 Quick wins (low effort, high leverage)

1. **`ForwardFileSpec.language="vue"`** from plan-ingestion emitter for `.vue` targets — unlocks existing `detect_language(..., explicit_lang)` path without waiting for extension map in obscure code paths.  
2. **Registry-only extension** for `.vue` → minimal change to `lang_detect` / Literal once profile exists.  
3. **Reuse `nodejs_parser` on extracted script** for Part B (already planned) — no second regex engine until Vue macros force it.  
4. **Prime `gen_context`**: two optional strings (`js_host_id`, `js_dialect_id`) — no new nested objects until consumers ask.

### 0.4 Essential complexity (keep)

- **Distinct `language_id` `vue`** with its own `LanguageProfile` (SFC is not a plain `.ts` file).  
- **Extract → transform → re-inject** pipeline for SFC (cannot be flattened away).  
- **Explicit repair/splice branching** so Python AST never runs on `.vue` raw text.

### 0.5 Non-goals (unchanged intent, explicit)

- Second parallel hint field on `ForwardFileSpec` **unless** `language` proves insufficient after one implementation iteration.  
- Nuxt / Vue 2 / CSS preprocessor depth as first deliverable (see end of doc).

---

## 1. Definitions

| Term | Meaning |
|------|---------|
| **JS host** | Shared ECMAScript-module / npm runtime assumptions, tooling hooks, and prompt “physics” that apply to plain `.js/.ts` **and** framework-specific file shapes. |
| **Framework dialect** | A distinguishable source shape (e.g. plain files on disk, Vue SFC) with its own extension map, extraction rules, and validation strategy. |
| **Plain Node dialect** | Current `nodejs` `LanguageProfile` behavior: single-language text files with extensions such as `.js`, `.ts`, `.tsx`, `.jsx`. |
| **Vue SFC dialect** | Single-file components: `.vue` with optional `<script lang="ts">`, `<template>`, `<style scoped>`, etc. |

---

## Part A — Abstraction layer (JavaScript host + n+1 dialects)

**Implementation plan:** [PLAN_PHASE_A_JS_HOST_ABSTRACTION.md](PLAN_PHASE_A_JS_HOST_ABSTRACTION.md)

### REQ-JSF-001 — Conceptual model

**Priority:** P0  
**Acceptance criteria:**

- The design SHALL treat **“JavaScript on Node”** as **one host** with **one or more framework dialects**, not as an unbounded set of unrelated `LanguageProfile` islands.
- **Plain Node** (current SDK behavior) SHALL be documented and implemented as **dialect index 0** / **first-class default** among `n+1` dialects for the same host.
- Additional dialects (minimum: **Vue**) SHALL plug in through the same abstraction without duplicating host-level concerns (npm, ESM/CJS patterns, common coding standards fragments).

### REQ-JSF-002 — Host vs dialect responsibilities

**Priority:** P0  
**Acceptance criteria:**

- **Host layer** SHALL own: npm/build file heuristics shared across dialects; baseline ECMAScript/TypeScript coding standards applicable across dialects; shared contamination / fingerprint utilities where meaningful; documentation of “when to add a new dialect vs new language.”
- **Dialect layer** SHALL own: file extensions and filename patterns; **extraction** of editable source from non-plain files (e.g. SFC blocks); dialect-specific validation commands; dialect-specific prompt role / supplements; MicroPrime element binding to **logical edit units** (e.g. script block body).

### REQ-JSF-003 — Backward compatibility

**Priority:** P0  
**Acceptance criteria:**

- Existing **`language_id` `nodejs`** and all current **`source_extensions`** for plain Node SHALL remain valid without migration of existing manifests, seeds, or tests.
- **`resolve_language`** and **`LanguageRegistry.get_extension_map()`** behavior for **non-Vue** projects SHALL be unchanged unless a new requirement explicitly tightens behavior (default: no regressions).

### REQ-JSF-004 — Registry and discovery

**Priority:** P1  
**Acceptance criteria:**

- Dialects MAY register via **entry points** (same group as existing languages) or an explicit sub-registry; the mechanism SHALL be documented in `CLAUDE.md` / developer docs.
- **`LanguageRegistry.discover()`** SHALL load host + dialects deterministically (ordering documented; plain Node remains the default when ambiguous).

### REQ-JSF-005 — Extension and build-file resolution

**Priority:** P0  
**Acceptance criteria:**

- **Globally unique** extension → dialect mapping: an extension (e.g. `.vue`) SHALL map to **at most one** `language_id` / dialect implementation.
- Build files (e.g. `package.json`, `vite.config.*`) MAY inform **host** detection and **dialect hints** but SHALL NOT alone flip dialect without a source file signal (avoid false positives in monorepos).

### REQ-JSF-006 — `resolve_language` integration

**Priority:** P0  
**Acceptance criteria:**

- Dominant-dialect selection for a feature’s `target_files` SHALL use **dialect-aware** extension counts **after** any per-file extraction class is known (e.g. a feature with only `.vue` files MUST resolve to **Vue dialect**, not default Python).
- **Sibling / batch context inference** (today used for “language-neutral” files) SHALL be updated so neutral files adjacent to **Vue** or **Node** sources infer the **correct dialect**, not only `nodejs` by accident.
- **Consistency:** When `ForwardFileSpec.language` is set for a path, dominant resolution and **`detect_language(..., explicit_lang=file_spec.language)`** (`micro_prime/lang_detect.py`) SHALL agree with **`resolve_language`** outcomes for the same batch (no third conflicting language string). Registering `vue` SHALL include updating the MicroPrime language detection path (Literal or `str`) so `vue` is not stuck as `unknown`.

### REQ-JSF-007 — Forward manifest / explicit overrides

**Priority:** P1  
**Acceptance criteria:**

- **`ForwardFileSpec.language`** (existing optional field, FR-DFA-009) SHALL be the **primary** override for plan-ingestion and manifest builders; values align with `language_id` (`python`, `nodejs`, `vue`, …). New parallel fields SHALL NOT be introduced unless `language` proves insufficient in a documented follow-up.
- Overrides SHALL be honored by **`resolve_language`** (or successor API) and by **MicroPrime routing** when building or consuming `ForwardManifest` / file specs.

### REQ-JSF-008 — MicroPrime routing API

**Priority:** P0  
**Acceptance criteria:**

- **`_is_non_python_file` / MicroPrime compatibility** SHALL NOT treat registered Vue extensions as “unknown → bypass MicroPrime” once Vue basic support (Part B) is implemented.
- The engine SHALL receive the **`LanguageProfile`** (or equivalent) needed to branch **Vue SFC** vs **plain Node** once Part B lands; **prefer** profile-driven routing over new parallel IDs until a second parser per `language_id` is required (see REQ-VUE-B-002 extraction + REQ-VUE-B-003 MicroPrime routing).

### REQ-JSF-009 — Prime Contractor generation context

**Priority:** P1  
**Acceptance criteria:**

- **`PrimeContractorWorkflow._build_generation_context`** SHALL expose both a **stable `language_id`** for the selected profile **and** a **host + dialect** breakdown where applicable, so prompts and validators can branch without string-matching file paths.

### REQ-JSF-010 — Tests and fixtures

**Priority:** P1  
**Acceptance criteria:**

- Unit tests SHALL cover: registry load order; extension map uniqueness; `resolve_language` for mixed batches (Vue + TS + neutral configs); backward compatibility matrix for existing Node-only fixtures.

---

## Part B — Basic Vue support (minimum viable)

**Implementation plan:** [PLAN_PHASE_B_VUE_BASIC.md](PLAN_PHASE_B_VUE_BASIC.md)

### B.0 — Prerequisite: Phase A complete

Part B SHALL NOT start until **Phase A** exit criteria in [PLAN_PHASE_A_JS_HOST_ABSTRACTION.md](PLAN_PHASE_A_JS_HOST_ABSTRACTION.md) are satisfied — specifically: **REQ-JSF-001–006** (model + registry + resolution + inference), **REQ-JSF-007** (forward-manifest hints), **REQ-JSF-008** (MicroPrime dialect routing hook), and **REQ-JSF-009** (`js_host_id` / `js_dialect_id` on `gen_context`).

**Refactoring rationale (original B-001 … B-010 → below):**

| Original ID | Change |
|-------------|--------|
| B-001 + B-003 | **Merged** into **REQ-VUE-B-001**: one profile REQ covers registry row + host/dialect metadata + prompt surfaces. |
| B-002 | **Narrowed**: dominant `.vue`-only resolution is **owned by REQ-JSF-006** once `.vue` maps to `vue`; Part B only adds **Vue-specific regression tests** (same REQ id, lighter AC). |
| B-004 | **Renamed focus** → **REQ-VUE-B-002** extraction as the **first Vue-only deliverable** after registration. |
| B-005 | **Aligned to A.5–A.6** → **REQ-VUE-B-003** MicroPrime uses **`js_dialect_id == vue_sfc`** (or equivalent) and **parser/splicer id** from Phase A hook, not ad-hoc path checks. |
| B-006 … B-010 | **Renumbered** to **REQ-VUE-B-005 … B-009** (validation → fixture); content tightened to reference host reuse and REQ-JSF-007 hints. |

---

### REQ-VUE-B-001 — `VueLanguageProfile` (registry + host alignment + prompts)

**Priority:** P0  
**Replaces:** legacy B-001 + B-003 (single profile deliverable).

**Acceptance criteria:**

- Register **`language_id` `vue`** with **`source_extensions`** containing `.vue` such that **`LanguageRegistry.get_extension_map()`** maps `.vue` → `vue` (REQ-JSF-005 uniqueness satisfied alongside `nodejs`).
- Set **`js_host_id`** to the **same canonical value** as `NodeLanguageProfile` (per Phase A ADR, e.g. `javascript_node`) and **`js_dialect_id`** to `vue_sfc` so Prime / MicroPrime / telemetry share one JS host namespace (REQ-JSF-001, REQ-JSF-002).
- Reuse **host-level** `coding_standards` fragments from the shared JS host module where possible; **dialect-specific** supplements SHALL document SFC structure, `<script setup>`, Composition API defaults, and **non-goals** for `<template>` / `<style>` in basic tier.
- **`build_file_patterns`** appropriate to Vue 3 + Vite (`package.json`, `vite.config.ts` / `.js`, `pnpm-lock.yaml`, etc.) without violating REQ-JSF-005 (build files hint host only).

**Phase A relationship:** Implements the first **n+1** dialect row; no separate “composite key” unless Phase A Option B was chosen.

---

### REQ-VUE-B-002 — SFC script extraction

**Priority:** P0  
**Formerly:** REQ-VUE-B-004.

**Acceptance criteria:**

- A documented, tested **extractor** converts a `.vue` file to **zero or one primary script block** (default: first `<script setup>` or first `<script>`; multiple scripts: explicit precedence + tests).
- Extracted text is valid **JS or TS** for downstream tooling; **`lang="ts"`** honored.
- Extractor output is the **logical edit unit** passed to MicroPrime / validators (REQ-JSF-002 dialect ownership).

**Phase A relationship:** Extraction runs **before** element counting if Phase A introduces a pre-resolution hook; otherwise extraction is internal to the `vue` dialect engine path wired in REQ-VUE-B-003.

---

### REQ-VUE-B-003 — MicroPrime minimal path (dialect-routed)

**Priority:** P1  
**Formerly:** REQ-VUE-B-005.

**Acceptance criteria:**

- MicroPrime selects **Vue SFC handling** via **Phase A routing** (`js_dialect_id` / `get_parser_id` equivalent, REQ-JSF-008), not by re-parsing file paths in scattered call sites.
- Operations on **extracted script text** for element detect / splice; **MUST NOT** corrupt `<template>` / `<style>` when only the script block changes.
- If **full-file LLM fallback** is used for MVP, it MUST be **feature-flagged or single-feature scoped**, dry-run tested, logged once per run, and tracked for removal under REQ-VUE-P-016.

**Phase A relationship:** `gen_context` already exposes host/dialect (REQ-JSF-009); Vue path **consumes** those keys.

---

### REQ-VUE-B-004 — Resolution regression (Vue-only batches)

**Priority:** P0  
**Formerly:** REQ-VUE-B-002 (duplicate of JSF-006).

**Acceptance criteria:**

- With **`vue` registered**, automated tests prove **`resolve_language`** on **only** `.vue` `target_files` returns the **`vue` profile** (not `python`, not `nodejs` unless tie-break rules intentionally say otherwise — document tie-break if `.vue` + `.ts` mixed).
- Neutral config files in the same batch infer **`vue`** when siblings are exclusively `.vue` (REQ-JSF-006 inference).

**Phase A relationship:** **Normative behavior** is REQ-JSF-006; this REQ is **Vue acceptance tests** so regressions are caught in Part B PRs.

---

### REQ-VUE-B-005 — Validation (basic)

**Priority:** P1  
**Formerly:** REQ-VUE-B-006.

**Acceptance criteria:**

- At least one automated path: **`vue-tsc --noEmit`**, or **`eslint` + `eslint-plugin-vue`**, operating on **SFC or extracted script** per tool capability; if unavailable, `syntax_check_command` MAY be **`None`** with an explicit **gap reference** to REQ-VUE-P-005.

**Phase A relationship:** None; tool-specific.

---

### REQ-VUE-B-006 — Repair pipeline safety

**Priority:** P1  
**Formerly:** REQ-VUE-B-007.

**Acceptance criteria:**

- No repair step runs **Python `ast`** or **Node TS validation on whole `.vue` text** unless the step explicitly unwraps to extracted script; violations **skip + log** at `WARNING` with `language_id=vue`.

**Phase A relationship:** dialect id in repair context comes from REQ-JSF-009 / file profile.

---

### REQ-VUE-B-007 — Plan ingestion, seeds, and forward hints

**Priority:** P2  
**Formerly:** REQ-VUE-B-008.

**Acceptance criteria:**

- Language summaries / seeds list **`vue`** when `.vue` targets exist (no silent “unknown”).
- For emitted `ForwardFileSpec` rows, set **`language="vue"`** (or the chosen `language_id`) on `.vue` paths so **`detect_language(..., explicit_lang=file_spec.language)`** and downstream consumers agree with **REQ-JSF-006** / **REQ-JSF-007** without parallel hint fields.

**Phase A relationship:** Implements **REQ-JSF-007** using the existing **`ForwardFileSpec.language`** field.

---

### REQ-VUE-B-008 — Documentation

**Priority:** P2  
**Formerly:** REQ-VUE-B-009.

**Acceptance criteria:**

- Developer doc: **Basic Vue** = script-block–centric; template/style limits; link to Part C; link to Phase A plan for host/dialect mental model.

---

### REQ-VUE-B-009 — Acceptance fixture

**Priority:** P1  
**Formerly:** REQ-VUE-B-010.

**Acceptance criteria:**

- In-repo fixture: minimal **Vue 3 SFC** + optional `package.json` / `vite.config` stub proving: register (**B-001**) → resolve regression (**B-004**) → extract (**B-002**) → MicroPrime path (**B-003**) → validate as far as **B-005** allows.

---

### Traceability: old Part B ID → new ID

| Old | New |
|-----|-----|
| REQ-VUE-B-001 | REQ-VUE-B-001 (expanded) |
| REQ-VUE-B-002 | REQ-VUE-B-004 |
| REQ-VUE-B-003 | REQ-VUE-B-001 (merged) |
| REQ-VUE-B-004 | REQ-VUE-B-002 |
| REQ-VUE-B-005 | REQ-VUE-B-003 |
| REQ-VUE-B-006 | REQ-VUE-B-005 |
| REQ-VUE-B-007 | REQ-VUE-B-006 |
| REQ-VUE-B-008 | REQ-VUE-B-007 |
| REQ-VUE-B-009 | REQ-VUE-B-008 |
| REQ-VUE-B-010 | REQ-VUE-B-009 |

---

## Part C — Full parity with Node.js (for Vue dialect)

**Implementation plan:** [PLAN_PHASE_C_VUE_PARITY.md](PLAN_PHASE_C_VUE_PARITY.md)

*Parity means: for workflows that today apply to **plain Node** files (`.ts`/`.tsx`/`.js`/…), the **Vue dialect** offers equivalent **capabilities** where the underlying file format allows. Some Node-only behaviors (e.g. `node --check` on `.ts`) may require **extracted temp files** or tool substitution — requirements allow implementation flexibility but demand **equivalent user-visible outcomes**.*

### C.0 — Prerequisites

Part C SHALL NOT start until:

- **Phase A** complete per [PLAN_PHASE_A_JS_HOST_ABSTRACTION.md](PLAN_PHASE_A_JS_HOST_ABSTRACTION.md) (REQ-JSF-001 … 010).
- **Part B** complete per [PLAN_PHASE_B_VUE_BASIC.md](PLAN_PHASE_B_VUE_BASIC.md): **REQ-VUE-B-001** (Vue profile + host alignment), **B-002** (extraction), **B-003** (dialect-routed MicroPrime), **B-004** (resolution regression), **B-005** (basic validation or documented gap), **B-006** (repair safety), **B-009** (acceptance fixture).

**Recommended before production / broad Prime batches:** **REQ-VUE-B-007** (plan-ingestion + **`ForwardFileSpec.language`** for `.vue`) and **B-008** (operator docs) — not strict blockers for starting Part C engineering on core parity streams.

### C.1 — Refactoring review (same pattern as Part B)

REQ IDs **P-001 … P-016 are retained** for external traceability. Changes from an earlier flat draft:

| REQ | Refactoring note |
|-----|------------------|
| **P-001** | Aligns `blast_radius_extensions` with **B-001** `source_extensions` + colocated `.ts` story; no Phase A change required beyond extension map. |
| **P-002** | **Deepens B-002/B-003**: element extraction on extracted script shall match `nodejs_parser` semantics where applicable — depends on Part B extractor + parser hook, not new resolution rules. |
| **P-003** | **Splice parity** — formalizes re-injection promised in **B-003**; adds ordering/attribute preservation beyond MVP. |
| **P-004** | **TypeScript-in-SFC** — paired with **P-005**: validation / tooling in P-005 SHALL cover `lang="ts"` paths defined here (single acceptance story split for readability). |
| **P-005** | **Commands parity** — closes **B-005** optional-`None` gap; MUST invoke or emulate checks that satisfy **P-004** for both JS and TS script blocks. |
| **P-006** | **Framework imports** — extends **B-001** prompt/registry surface with Vue ecosystem entries (same schema as Node `framework_imports`). |
| **P-007** | **Cleanup patterns** — extends **REQ-JSF-002** host list; Vue-specific dirs only (no duplicate host-level npm noise). |
| **P-008** | **Complexity routing** — uses **gen_context** `js_host_id` / `js_dialect_id` (REQ-JSF-009); parity with Node thresholds. |
| **P-009** | **Repair parity** — extends **B-006** from “do no harm” to “equivalent taxonomy + outcomes” vs Node repair on `.ts`. |
| **P-010** | **Explicit non-bypass** — **parity** counterpart to **B-003** minimal path: same guarantees as Node’s non-bypass MicroPrime happy path, tested. |
| **P-011** | **Template/style** — optional tier; independent of Phase A. |
| **P-012** | **Telemetry** — ensures `language_id` + dialect keys match **nodejs** cardinality (builds on REQ-JSF-009). |
| **P-013** | **Idempotent extract/splice** — tightens **B-002**/**P-003** for caching and newline stability. |
| **P-014** | **Security prompts** — host text from Phase A module + Vue-specific XSS/template notes (with **P-006**). |
| **P-015** | **Regression suite** — superset of **B-009** fixture across engine/repair/prime. |
| **P-016** | **Deprecation** — removes **B-003** LLM fallback and **B-005** gaps per milestone (unchanged intent). |

### REQ-VUE-P-001 — Extension and blast radius parity

**Priority:** P1  
**Acceptance criteria:**

- **`blast_radius_extensions`** (or successor) for Vue includes at least `.vue` and aligns with project conventions for colocated `.ts` types (documented).

### REQ-VUE-P-002 — Element extraction parity

**Priority:** P1  
**Acceptance criteria:**

- Element discovery on extracted script code achieves **coverage and limitation parity** with `nodejs_parser` for the same syntactic patterns (functions, classes, `const` arrows, interfaces, type aliases), modulo Vue-specific syntax (e.g. `defineProps`) documented as supported or explicitly out-of-scope with tests.

### REQ-VUE-P-003 — Splicing parity

**Priority:** P1  
**Acceptance criteria:**

- Post-generation splice **re-injects** modified script into the SFC with **stable ordering** of blocks (`<script>` / `<template>` / `<style>`), preserving attributes (`lang`, `setup`, `scoped`) and **no unintended formatting loss** beyond documented normalization.

### REQ-VUE-P-004 — TypeScript inside SFC

**Priority:** P0  
**Part C relationship:** TypeScript semantics here are **exercised by** **REQ-VUE-P-005** tooling (no `None` gap once P-005 parity is claimed).

**Acceptance criteria:**

- **`lang="ts"`** and default script treated as JS both work; TypeScript validation path matches Node profile rigor (see existing Node TS validation patterns in `NodeLanguageProfile`).

### REQ-VUE-P-005 — Validation parity

**Priority:** P1  
**Part C relationship:** **Closes** optional validation gap from **REQ-VUE-B-005**; MUST validate **`lang="ts"`** per **REQ-VUE-P-004**.

**Acceptance criteria:**

- **`syntax_check_command`** / lint hooks: either invoke project-local **Vue + TS** toolchain with `{file}` semantics **or** documented equivalent using extraction + temp file, with CI-friendly exit codes.
- **`test_command`** parity: if Node profile returns `npm test`, Vue profile SHALL return the same **or** framework-appropriate documented default (`pnpm`/`vite` test) selected consistently from manifest hints.

### REQ-VUE-P-006 — Framework imports registry

**Priority:** P2  
**Acceptance criteria:**

- **`framework_imports`** includes Vue 3 ecosystem entries (`vue`, `vue-router`, `pinia`, common testing libs) analogous in structure to Node profile’s `framework_imports`.

### REQ-VUE-P-007 — Cleanup and merge patterns

**Priority:** P2  
**Acceptance criteria:**

- **`cleanup_patterns`** includes Vue/Vite artifacts (`dist/`, `.vite/`, etc.) where applicable, aligned with host layer policy (REQ-JSF-002).

### REQ-VUE-P-008 — Complexity routing parity

**Priority:** P1  
**Acceptance criteria:**

- **Complexity tier / routing** for `.vue` tasks matches Node policy (same thresholds or documented deltas with rationale and tests).

### REQ-VUE-P-009 — Repair pipeline parity

**Priority:** P1  
**Acceptance criteria:**

- All **language-aware repair steps** that run for `nodejs` on `.ts`/`.js` either run on **extracted Vue script** with equivalent outcomes or have a **Vue-specific** repair step with the same contract violation taxonomy coverage.

### REQ-VUE-P-010 — Prime adapter / bypass behavior

**Priority:** P1  
**Acceptance criteria:**

- **`MicroPrimeCodeGenerator`** paths for Vue do not rely on accidental “unknown extension bypass”; behavior is **explicit** and tested (parity with Node’s non-bypass happy path).

### REQ-VUE-P-011 — `<template>` and `<style>` (scoped parity)

**Priority:** P2  
**Acceptance criteria:**

- Documented support level for edits inside `<template>` (e.g. LLM-only vs structured) and `<style scoped>`; if out of scope, **explicit guardrails** prevent silent corruption. Long-term: optional **sub-block** contracts mirroring script extraction.

### REQ-VUE-P-012 — Observability and Kaizen hooks

**Priority:** P2  
**Acceptance criteria:**

- Language / dialect appears in telemetry and Kaizen artifacts consistently with `nodejs` (no “unknown” regression for Vue runs).

### REQ-VUE-P-013 — Performance and caching

**Priority:** P3  
**Acceptance criteria:**

- Extraction + re-splice is **idempotent** for unchanged elements; checksum / element-id strategy documented to avoid thrashing on Windows vs POSIX newlines.

### REQ-VUE-P-014 — Security and dependency prompts

**Priority:** P2  
**Acceptance criteria:**

- Vue dialect inherits **host-level** security guidance; Vue-specific XSS/template safety notes appear in **`coding_standards`** or security contract hooks equivalent to Node.

### REQ-VUE-P-015 — Regression suite

**Priority:** P0  
**Acceptance criteria:**

- Dedicated test module mirrors **`tests/` coverage depth** for Node micro-prime wiring (resolution, engine, repair, prime contractor context) for Vue fixtures of increasing complexity (single-file, TS script, multiple components).

### REQ-VUE-P-016 — Deprecation policy

**Priority:** P2  
**Acceptance criteria:**

- Any temporary MVP behavior from Part B is **flagged**, **logged once per run**, and **removed or promoted** to parity within a versioned milestone (documented in changelog).

---

## Traceability matrix (summary)

| Area | Part A (JSF) | Part B (Vue basic) | Part C (Vue parity) |
|------|--------------|--------------------|---------------------|
| Registry / discover | REQ-JSF-003,004,005 | REQ-VUE-B-001 | REQ-VUE-P-001 |
| resolve_language | REQ-JSF-006 (normative) | REQ-VUE-B-004 (Vue regression tests) | — |
| LanguageProfile | REQ-JSF-002,009 | REQ-VUE-B-001 | REQ-VUE-P-005,006,007 |
| MicroPrime | REQ-JSF-008 | REQ-VUE-B-002,003 | REQ-VUE-P-002,003,009,010 |
| Validation | — | REQ-VUE-B-005 | REQ-VUE-P-004,005 |
| Repair | — | REQ-VUE-B-006 | REQ-VUE-P-009 |
| Plan / forward hints | REQ-JSF-007 | REQ-VUE-B-007 | — |
| Templates / styles | REQ-JSF-002 | — | REQ-VUE-P-011 |
| Tests | REQ-JSF-010 | REQ-VUE-B-009 | REQ-VUE-P-015 |

---

## Non-goals (this draft)

- Nuxt / Vue 2 Options-only ecosystem as **first** deliverable (may follow under same dialect or sub-dialect).
- CSS preprocessor parity (SCSS, Less) unless explicitly added in REQ-VUE-P-011 follow-ons.

---

*v0.2 — Post-planning self-reflective update: §0 Planning insights added; REQ-JSF-006–008 and REQ-VUE-B-007 tightened to reuse `ForwardFileSpec.language` and profile-first routing; Part C.0 adds recommended B-007/B-008; accidental-complexity cuts documented in §0.1.*

*End of draft — revise IDs and priorities after architecture review.*
