# SDK Node Home — Requirements

**Project:** startd8-sdk   **Criticality:** high
**Version:** 0.4   **Date:** 2026-08-14
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** `PLAN-01-sdk-node-home.md`
**Inherits standards:** det-req-kit · NODE-SCHEMA v0.3.9 · HOWTO-VISUALIZE-A-REQUIREMENT · VISUAL-REQUIREMENTS-DEFINER-ROADMAP (no 2nd renderer/grammar/store)
**Audience:** operator
**Trust boundary:** local filesystem + authored manifests only; no network fetch of evidence
**Data classification:** internal

## 0. Planning Insights (Self-Reflective Update)

> What changed between v0.1 (pre-planning) and v0.2 (post-planning). Planning against
> ContextCore `navigator/` + startd8 `wireframe{,_view}/` revealed 7 corrections:

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| SDK invents a Node model | CC already ships field-complete `Node` / `NodeEvidence` / `derive_status` (+ axes, facets) in `navigator/models.py` | FR-1 = **port field-compatible surface into SDK**; Mottainai, not redesign |
| WireframeItem must be redesigned | CC `nodes_to_wireframe_plan` already projects Node→WireframeItem but **flattens** `lives`→`paths` and drops type/confidence/`ships_when` | FR-2 = additive optional fields + compose pass-through; keep `paths` for back-compat |
| Gap exclusion edits `GAP_STATUSES` | App gap set is `{not_defined,placeholder,invalid}` — Node vocab is built/thin/spec; honest-skips are `route_state` | FR-3 Verify uses **route_state / profile.is_gap**, not stuffing Node statuses into GAP_STATUSES |
| Requirements source is greenfield | CC `sources_requirements.py` is V-1..V-5 (~900 LOC); det-req-kit `extract.py` already parses `Lives:` + `fr_health` | FR-6 narrowed to **minimal FR→Node** (reuse extract parsing; defer full plan-DAG parity) |
| Projection stays in CC | Working adapter is `render.py:nodes_to_wireframe_plan` | New FR-10: projection **lives in SDK**; CC may later call it |
| Contract Projection used `subcommand` for library modules | Closed `python-cli-surface` kinds are CLI-only | Projection table CLI-only; library seams cited as **file paths** in Touches |
| CLI could reuse `nav` | `startd8 nav` already = generated-app top-nav registry | Confirmed: Typer group **`navigator`** only (NR-6) |

**Resolved open questions:**
- **OQ-1 (where does Node live?) → SDK `src/startd8/navigator/`.** Phase 1 = **copy port** (field-compatible); shared package deferred. CC import of SDK Node = follow-on (not Phase 1 acceptance); Phase 1 does **not** rewrite ContextCore.
- **OQ-2 (full det-req parity?) → No.** Minimal FR cards + Lives + Verify/health; V-1..V-5 plan DAG = Phase 1.1 / follow-on.
- **OQ-3 (second renderer?) → No.** HTML remains `wireframe_view` + RenderProfile (NR-3).
- **OQ-4 (extract coupling?) → vendor_thin default.** Vendored thin Lives/`fr_health` helper cited to det-req-kit; optional `DET_REQ_KIT` subprocess; **no** required sibling-path import (CRP R1).
- **OQ-5 (WireframeItem shape?) → additive optional fields.** Not a companion meta bag; compose **omits** empty Node keys (CRP R1).

### 0.1 Lessons-Learned Hardening (v0.3)

> Design-docs lessons base consulted (`Design_Docs_LESSONS_LEARNED.md`). ContextCore
> `lesson recall` MCP unavailable in this environment — recorded as checked-empty.

- **[Vocabulary single-source / Leg 5]** — Do not restate NODE-SCHEMA field lists as a second normative vocab → Contract Projection cites SCHEMA §8 + NODE-SCHEMA; Node field set is "cite NODE-SCHEMA", not a forked enum in this REQ.
- **[Phantom-reference audit / Leg 6 #6/#13]** — `startd8.navigator.*` does **not** exist yet → every new symbol marked *to-be-created* in plan F-1; existing symbols (`WireframeItem`, `compose.GAP_STATUSES`, `cli nav`) grepped and real.
- **[Mottainai / reuse]** — Prefer port of CC models + `nodes_to_wireframe_plan` and reuse det-req `extract` lives parsing over a third FR parser → FR-1/FR-6/FR-10 wording tightened.

### 0.2 Design-Principle Hardening (v0.3.1)

- **[Mottainai]** — No second HTML backend / no Studio-only req store (NR-3); port CC Node rather than invent → FR-1, FR-10.
- **[Genchi Genbutsu]** — Bind to real `WireframeItem`, `compose.py` need_items, live `cli.py` `nav` collision, live capability YAML v1.27.0 → FR-7/FR-8 Verifies name those paths.
- **[Hitsuzen]** — Status + default confidence are **derived**, never LLM-authored → FR-3, FR-4.
- **[Context-Correctness-by-Construction]** — Typed lives/confidence/ships_when must appear in compose JSON (today they silently die at the paths flatten) → FR-2 Verify.
- **[Accidental-Complexity]** — Do not grow an enumerated Node-status allowlist inside GAP_STATUSES; one rule: honest-skip `route_state` ⇒ not a gap (`is_gap=False` / excluded from need_items) → FR-3.
- **[Backend routing]** — FRs are operator CLI + library; header stays `python-cli-surface`; library Touches use file paths (not fake `subcommand` kinds).

## Overview

Phase 1 of the requirements-visualization ladder
([`TOP_DOWN_IMPROVEMENT_PLAN.md`](./TOP_DOWN_IMPROVEMENT_PLAN.md)): make the startd8 SDK a
**first-class Node home** so operators can project the capability-index and det-req docs into
glance-approvable HTML/JSON **without ContextCore as the sole ingest path**. The SDK already owns
the domain-agnostic wireframe HTML renderer; this work ports a field-compatible Node model,
preserves typed grounding through compose, adds sources + CLI + a `$0` grounding pass. ContextCore
keeps the a11y cockpit (NR-2); the Definer remains the up-ladder authoring seat (Phase 3).

## Objectives

- O-1: An operator can render the SDK capability-index and a det-req doc as Nodes via `startd8 navigator build` — target: exit 0 with HTML or JSON containing live keys.
- O-2: Rendered nodes preserve typed `lives` (prefer `git:<sha>:<path>`), optional `confidence`, and `ships_when` iff `lives` empty — target: unit tests assert compose JSON round-trip.
- O-3: Hand-navigator Level-1 landscapes can be regenerated from a `$0` grounding pass — target: deterministic JSON of key→mention counts + ISO date, no LLM.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| quality | Incompatible Node twin vs ContextCore | Field-compatible port; later CC can import SDK; no schema fork | high |
| quality | App-wireframe byte drift when extending WireframeItem | Optional fields default empty; `test_no_profile_is_byte_identical` + determinism tests stay green | high |
| quality | Re-implementing det-req parsing (drift from kit) | Default **vendor_thin** Lives/`fr_health` cited to kit SCHEMA/extract; optional `DET_REQ_KIT` subprocess; never require sibling-path import | high |
| availability | CLI name collides with `startd8 nav` | Typer group `navigator` only | medium |
| scope-creep | Porting full V-1..V-5 requirements source + a11y cockpit | FR-6 minimal; NR-2 / NR-7 | medium |

## Profile

Declared profile: **internal**

## Functional requirements

- **FR-1 — Node model in the SDK.** The SDK exposes a frozen Node + NodeEvidence + derive_status surface field-compatible with ContextCore's `navigator/models.py` and NODE-SCHEMA (`key`, `does`, `wont`, `lives[]`, `ships_when`, `confidence`, `triggers`, `children`, `category`, `orientation`, `route_state`; optional `status_facets` / `attributes` for compatibility). Name: SDK exposes a NODE-SCHEMA-compatible Node · NodeEvidence · derive_status surface so navigators keep typed grounding without ContextCore. Touches: `src/startd8/navigator/models.py`. Lives: code src/startd8/navigator/models.py. Approve?: does the Node field set match NODE-SCHEMA?. Verify: `derive_status(has_code_evidence=True, maturity="beta")` returns **`built`**; `maturity="alpha"` (or development/experimental) returns **`thin`**; a field-compat golden (shared field names/types vs a pinned NODE-SCHEMA / frozen fixture — **no** `import contextcore`) passes. Serves: O-2
- **FR-2 — Typed grounding survives compose.** WireframeItem gains optional `key`, `lives` (typed tuples), `confidence`, `ships_when`, `was`, `route_state` (defaults empty/None); `compose` `_item_view` emits them **only when set** (omit-when-empty). Existing `paths` remains populated from lives refs for back-compat. Touches: `src/startd8/wireframe/plan.py`, `src/startd8/wireframe_view/compose.py`. Lives: code src/startd8/wireframe/plan.py. Lives: code src/startd8/wireframe_view/compose.py. Approve?: are typed lives visible in compose JSON when set · omitted when empty?. Verify: (a) navigator Node with typed lives + confidence 0.9 → compose item JSON includes type+ref and confidence; (b) classic app WireframeItem compose JSON gains **no** new keys. Serves: O-2
- **FR-3 — Derived status + honest-skip gap rule.** Status is derived from evidence × maturity; nodes with `route_state` in `{owned_elsewhere, declared_unimplemented}` are excluded from attention/gap counts (profile `is_gap=False` or need_items filter) — do **not** overload app `GAP_STATUSES`. When no RenderProfile is passed (app path) and `route_state` is empty, existing `GAP_STATUSES` need_items behavior is unchanged. Touches: `src/startd8/navigator/models.py`, `src/startd8/wireframe_view/compose.py`, `src/startd8/wireframe/profile.py`. Lives: code src/startd8/wireframe_view/compose.py. Verify: ships_when-only + `route_state=declared_unimplemented` absent from `need_items`; app-plan need_items golden unchanged. Serves: O-2
- **FR-4 — Default confidence heuristic (SDK-owned).** When confidence is unset, `default_confidence(lives)` (★ SDK-owned — **not** a CC port) computes the wireframe-navigator rubric (0.9 code+test · 0.6 partial/doc-only · 0.4 pure spec). Touches: `src/startd8/navigator/models.py`, `tests/unit/navigator/test_models.py`. Lives: code src/startd8/navigator/models.py. Approve?: does 0.9 require BOTH code and test lives?. Verify: code+test lives and no authored confidence ⇒ 0.9 (±ε); helper exists only under `startd8.navigator`. Serves: O-2
- **FR-5 — Capability-index source.** Project `docs/capability-index/startd8.sdk.capabilities.yaml` (path override allowed) into Nodes with derived status and typed evidence/`wont`. Touches: `src/startd8/navigator/sources_capability.py`, navigator-build. Lives: code src/startd8/navigator/sources_capability.py. Verify: `startd8 navigator build --source capability-index --format json` exits 0 and JSON contains ≥1 live `capability_id` from the v1.27.0+ manifest. Serves: O-1
- **FR-6 — Minimal det-req requirements source.** Project a det-req/0.1 file into FR Nodes (does / Verify / Touches / optional evidence locators / derived fr_health). Default coupling = **vendor_thin** evidence/`fr_health` helper with SCHEMA/extract cite; optional `DET_REQ_KIT` subprocess; forbid required sibling-path import; do not fork the kit schema. Full V-1..V-5 plan-DAG parity is out of scope. Touches: `src/startd8/navigator/sources_requirements.py`, `tests/unit/navigator/test_sources_and_cli.py`, navigator-build. Lives: code src/startd8/navigator/sources_requirements.py. Lives: code src/startd8/navigator/det_req.py. Approve?: is vendor_thin enough for CI without a sibling kit?. Verify: fixture REQ with a commit-anchored code locator builds exit 0 with typed evidence; done-claim without locator ≠ grounded; unit tests pass with det-req-kit **absent** from `sys.path`. Serves: O-1
- **FR-7 — Navigator CLI.** Typer group `startd8 navigator` exposes `build` with `--source`, `--format` (`html`|`json`), `--out`; must not register as `nav`. Touches: navigator-build, exit-navigator, `src/startd8/cli.py`. Lives: code src/startd8/navigator/cli_navigator.py. Lives: code src/startd8/cli.py. Verify: one smoke test — `startd8 navigator --help` lists `build`/`ground`; `startd8 nav --help` still documents the app top-nav registry. Serves: O-1
- **FR-8 — App-path byte identity.** Classic app-scaffold wireframe with no Node fields / no profile remains byte-identical (HTML profile path **and** compose JSON omit-when-empty). Touches: `src/startd8/wireframe/plan.py`, `tests/unit/wireframe/test_render_profile.py`, `tests/unit/wireframe/test_determinism_and_json.py`. Lives: test tests/unit/wireframe/test_render_profile.py. Approve?: is the classic app compose JSON keyset unchanged (no new keys)?. Verify: `test_no_profile_is_byte_identical` + canonical JSON determinism pass without golden edits; classic compose JSON keyset unchanged. Serves: O-2
- **FR-9 — Automated grounding pass.** `$0` command enumerates FR- / capability_id keys under a tree, counts code mentions, emits dated grounding JSON. Touches: navigator-ground, exit-navigator. Lives: code src/startd8/navigator/ground.py. Verify: `startd8 navigator ground --root src --out /tmp/ground.json` exits 0; JSON has keys, integer counts, ISO date. Serves: O-3
- **FR-10 — Projection in the SDK.** `nodes_to_wireframe_plan(nodes, *, project_root, group_by)` lives in the SDK (port of CC `navigator/render.py`); HTML render reuses `wireframe_view.render_to_file` + optional RenderProfile. Touches: `src/startd8/navigator/project.py`, `src/startd8/wireframe_view/`. Lives: code src/startd8/navigator/project.py. Verify: unit test builds a plan from two Nodes without importing ContextCore; `html` format writes a file. Serves: O-1

## Non-goals

- NR-1: Interactive / 3D fsn navigator.
- NR-2: Owning ContextCore a11y cockpit / `render_a11y.py` / Tier-2–3 lesson·principle flags.
- NR-3: A second HTML renderer or a Studio-only requirements store.
- NR-4: Auto-generating kickoff/wireframe navigator README markdown (OQ-5) — grounding JSON only.
- NR-5: Facet/search HTML modes (NODE-SCHEMA §3a).
- NR-6: Renaming or removing `startd8 nav`.
- NR-7: ContextCore worktree ↔ `origin/main` bidirectional merge (ops).
- NR-8: Full V-1..V-5 requirements visualization parity (plan DAG, objectives frame) — follow-on.

## Owned fields

Only humans enter: authored `wont` / `does` in source docs; `ships_when` activation text; optional
authored `confidence` overrides; WAS/alias notes when rebranding.

## Contract projection

- **Backend:** python-cli-surface
- **Vocabulary home (cite):** `~/Documents/dev/dev-os/det-req-kit/SCHEMA.md` §8 `python-cli-surface` · living homes `~/Documents/dev/startd8-sdk/pyproject.toml`, `~/Documents/dev/startd8-sdk/src/startd8/cli.py` · grammar cite `~/Documents/dev/dev-os/NODE-SCHEMA.md`

| Entry (name) | Kind | Words/Structure | Notes |
|--------------|------|-----------------|-------|
| startd8 | console-script | structure | existing `startd8 = "startd8.cli:app"` |
| navigator-build | command | structure | `startd8 navigator build` (new; not `nav`) |
| navigator-ground | command | structure | `startd8 navigator ground` |
| exit-navigator | exit-class | structure | 0 = wrote artifacts; non-zero = parse/IO failure |
| source-capability-index | option | structure | `--source capability-index` |
| source-requirements | option | structure | `--source requirements` + requirements path |
| format-html | option | structure | `--format html` |
| format-json | option | structure | `--format json` |

Library seams (not CLI kinds — cite as Touches file paths): `src/startd8/navigator/models.py`,
`sources_capability.py`, `sources_requirements.py`, `project.py`, `ground.py`;
`src/startd8/wireframe/plan.py`; `src/startd8/wireframe_view/compose.py`.

## Appendix A — Accepted (with where merged)
## Appendix B — Rejected (with rationale)
## Appendix C — Incoming review rounds

*v0.4 — Post CRP R1 triage (all 5 F + focus locks merged). Ready for implementation.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-F1 | `default_confidence` is SDK-owned, not a CC port | CRP R1 | Merged FR-4 + OQ; PLAN Design table corrected | 2026-08-14 |
| R1-F2 | Compose omit-when-empty for Node keys | CRP R1 | Merged FR-2 Verify (a)/(b) + FR-8 | 2026-08-14 |
| R1-F3 | FR-6 coupling = vendor_thin + optional DET_REQ_KIT | CRP R1 | Merged FR-6 + Risks + OQ-4 | 2026-08-14 |
| R1-F4 | beta → built; alpha → thin | CRP R1 | Merged FR-1 Verify | 2026-08-14 |
| R1-F5 | App path GAP_STATUSES unchanged when route_state empty | CRP R1 | Merged FR-3 Verify | 2026-08-14 |
| Focus 1–4 | Port-now; vendor_thin; additive fields; CC follow-on OK | CRP R1 | Merged OQ-1..OQ-5 | 2026-08-14 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none) |  |  | All R1 F-suggestions accepted | 2026-08-14 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — composer-2 — 2026-08-14 UTC

- **Reviewer**: composer-2
- **Date**: 2026-08-14 16:10:00 UTC
- **Scope**: Dual-doc CRP R1 — focus asks + requirements ambiguity / acceptance criteria (Feature Requirements); paired with PLAN-01 R1 S-suggestions

##### Focus-file asks

**Ask 1 — Port vs shared package**

- **Summary answer:** Port (copy) into `startd8.navigator` now; do **not** extract a shared package in Phase 1.
- **Rationale:** §0 OQ-1 already resolves Node home to SDK with field-compat for a *later* CC import; Phase 1 "does **not** rewrite ContextCore." A shared package would invent a third packaging owner before any twin consumer exists. Drift is managed by NODE-SCHEMA cite + field-compat Verify (FR-1), not a new package.
- **Assumptions / conditions:** Dependency direction holds (startd8 must not import ContextCore); shared extract waits until CC imports SDK.
- **Suggested improvements:**
  - §0 Resolved OQ-1: add one sentence "Phase 1 = copy port; shared module deferred."
  - FR-1 Verify: add field-name/type golden vs NODE-SCHEMA (no CC import).

**Ask 2 — extract.py coupling**

- **Summary answer:** Default to a **vendored thin Lives/`fr_health` helper** cited to det-req-kit; optional subprocess when kit path is configured — do not require sibling-checkout import.
- **Rationale:** FR-6 text "reuse det-req-kit extract parsing for Lives — do not fork the kit schema" and Risks row "import or subprocess" leave packaging ambiguous. Unit tests and installed wheels cannot assume `~/Documents/dev/dev-os/det-req-kit`. Minimal FR-6 only needs Lives parse + groundedness, not the full ~extract projector.
- **Assumptions / conditions:** Kit is not a published startd8 dependency in Phase 1; SCHEMA remains normative cite, not a forked enum in this REQ.
- **Suggested improvements:**
  - FR-6: replace "import or subprocess" with a chosen default + optional override.
  - Verify: fixture path works with kit absent from `sys.path`.

**Ask 3 — WireframeItem additive fields vs companion dict**

- **Summary answer:** Additive optional fields on `WireframeItem` (FR-2 as written); not a companion dict for typed grounding.
- **Rationale:** FR-2 already names concrete fields (`key`, `lives`, `confidence`, `ships_when`, `was`, `route_state`) — a bag would undercut "typed tuples" and the compose JSON Verify. Compose today emits only `paths` among path-like data (`_item_view`); empty new keys must be omitted or FR-8 app-path identity fails in practice.
- **Assumptions / conditions:** Defaults empty/None; app builders leave them unset.
- **Suggested improvements:**
  - FR-2 Verify: add "classic app WireframeItem compose JSON gains **no** new keys."
  - FR-8: note compose omit-when-empty alongside HTML profile byte-identity tests.

**Ask 4 — CC follow-on**

- **Summary answer:** Acceptable Phase-1 incomplete state; do **not** require a CC thin-shim iteration to close FR-1..FR-10.
- **Rationale:** NR-2 / NR-7 and §0 OQ-1 already defer CC ownership/merge. Making CC import a Phase-1 gate would contradict non-goals and dependency direction. Naming the deferred handoff in PLAN (not this REQ body) is enough.
- **Assumptions / conditions:** FR-1 field-compat Verify is the Phase-1 twin fence; CC rewrite remains follow-on.
- **Suggested improvements:**
  - Optional one-liner under §0 OQ-1: "CC import of SDK Node = follow-on, not Phase 1 acceptance."
  - Do not weaken NR-2/NR-7.

##### Executive summary

- Focus asks align with settled §0 locks; main REQ gaps are testability and packaging clarity.
- FR-4 / PLAN Design disagree on whether `default_confidence` is a CC port (phantom) — clarify SDK-owned helper (R1-F1).
- FR-2/FR-8 need omit-when-empty compose acceptance (R1-F2).
- FR-6 coupling must be normative, not "import or subprocess" (R1-F3).
- FR-1 Verify "thin-or-built" for beta maturity is underspecified vs CC `derive_status` (beta → built) (R1-F4).

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Architecture | high | Clarify FR-4 / FR-1: default confidence heuristic is an ★ SDK-owned function (name e.g. `default_confidence`), **not** a field-compatible port from CC `navigator/models.py`. | FR-1 lists port surface including derive_status; FR-4 states the rubric; PLAN Design currently claims porting `default_confidence` from CC — that symbol does not exist in CC models (confidence set in sources). Untestable "port" claim. | FR-4 Touches / Verify; optionally FR-1 parenthetical | Unit: code+test lives, confidence unset ⇒ 0.9; grep proves helper lives in SDK only |
| R1-F2 | Data | high | Extend FR-2 Verify (and FR-8 if needed): compose item JSON includes typed lives/confidence **when set**, and **omits** those keys when WireframeItem defaults are empty (app path). | FR-2 Verify only asserts the positive navigator case. `_item_view` today has fixed keys; always-emitting `lives: []` / `confidence: null` would change every app compose payload and fight FR-8. | FR-2 Verify sentence; FR-8 Verify cross-ref | Two fixtures: navigator Node round-trip has type+ref; classic app compose JSON keyset unchanged |
| R1-F3 | Interfaces | high | Make FR-6 coupling normative: default = vendored thin Lives/`fr_health` cited to det-req-kit SCHEMA/extract; optional env-gated subprocess; forbid required sibling-path import. | Risks table already lists "import or subprocess" as mitigation without choosing — leaves FR-6 Verify packaging-undefined for CI/PyPI. | FR-6 body + Risks quality row on det-req parsing | Fixture build exit 0 without kit on `PYTHONPATH`; SCHEMA cite present in module docstring |
| R1-F4 | Validation | medium | Tighten FR-1 Verify: for `derive_status(has_code_evidence=True, maturity="beta")` expect **built** (not "thin-or-built"); reserve thin for alpha/development/experimental per CC/NODE-SCHEMA rule. | Current wording "returns thin-or-built per NODE-SCHEMA" is ambiguous — two implementers can pick opposite statuses for beta. CC `derive_status` returns BUILT for beta. | FR-1 Verify clause | Unit asserts `== "built"` for beta; `== "thin"` for alpha |
| R1-F5 | Risks | medium | Add FR-3 acceptance note: when no RenderProfile is passed (app path), empty `route_state` ⇒ existing `GAP_STATUSES` need_items behavior unchanged; navigator path applies honest-skip exclusion via `route_state` and/or profile `is_gap=False`. | FR-3 Touches `profile.py` and compose but Verify only shows the navigator honest-skip case. Dual-path interaction with app GAP_STATUSES is easy to break. | FR-3 Verify | App plan need_items golden unchanged; navigator fixture excludes `declared_unimplemented` |
