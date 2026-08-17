<!-- GENERATED det-plan/0.1 — projected $0 from the paired det-req by startd8 plan_codegen; do not edit by hand -->

# The SDK is the forward home for the Node model and the requirements-as-Nodes navigator, porting ContextCore's field-complete Node/derive_status surface and rendering a requirements doc as its dogfood without a second renderer, grammar, or store. — Implementation Plan (det-plan/0.1)

- **version:** 0.1
- **formatVersion:** det-plan/0.1
- **pairsWith:** `REQ-01-sdk-node-home.md`
- **companionKind:** PLAN
- **maturity:** 0.1
- **handle:** `plan/the-sdk-is-the-forward-home-for-the-node-model-18ff88ef`
- **ref:** `cc:intent:requirements-visualization:plan:req-01`

> A **det-plan is a `$0` projection of a det-req** — this document is derived, never authored. Its FR grouping and ordering are the requirement's authored structure; the strategic build-ordering strategy is the human's to add (the human-gated residue).

## Iterations

_19 iteration(s); costClass rollup: 19 llm-integration._

### F-1 — SDK exposes a NODE-SCHEMA-compatible Node · NodeEvidence · derive_status surface so navigators keep typed grounding without ContextCore

- **FRs:** FR-1
- **targetFiles:** `src/startd8/navigator/models.py`
- **dependsOn:** — (no authored dependency)
- **costClass:** llm-integration
- **status:** planned
- **gate (from the FRs' `Verify:`):**
  - FR-1: `derive_status(has_code_evidence=True, maturity="beta")` returns **`built`**; `maturity="alpha"` (or development/experimental) returns **`thin`**; a field-compat golden (shared field names/types vs a pinned NODE-SCHEMA / frozen fixture — **no** `import contextcore`) passes

### F-2 — WireframeItem carries optional typed grounding fields that compose emits only when set, keeping navigator grounding without changing the classic app path

- **FRs:** FR-2
- **targetFiles:** `src/startd8/wireframe/plan.py`, `src/startd8/wireframe_view/compose.py`
- **dependsOn:** — (no authored dependency)
- **costClass:** llm-integration
- **status:** planned
- **gate (from the FRs' `Verify:`):**
  - FR-2: (a) navigator Node with typed lives + confidence 0.9 → compose item JSON includes type+ref and confidence; (b) classic app WireframeItem compose JSON gains **no** new keys

### F-3 — navigator derives status from evidence and maturity and excludes owned-elsewhere or declared-unimplemented nodes from gap counts without overloading the app GAP_STATUSES

- **FRs:** FR-3
- **targetFiles:** `src/startd8/navigator/models.py`, `src/startd8/wireframe/profile.py`, `src/startd8/wireframe_view/compose.py`
- **dependsOn:** — (no authored dependency)
- **costClass:** llm-integration
- **status:** planned
- **gate (from the FRs' `Verify:`):**
  - FR-3: ships_when-only + `route_state=declared_unimplemented` absent from `need_items`; app-plan need_items golden unchanged

### F-4 — the SDK owns a default_confidence rubric that scores a node from its lives evidence when confidence is unset

- **FRs:** FR-4
- **targetFiles:** `src/startd8/navigator/models.py`, `tests/unit/navigator/test_models.py`
- **dependsOn:** — (no authored dependency)
- **costClass:** llm-integration
- **status:** planned
- **gate (from the FRs' `Verify:`):**
  - FR-4: code+test lives and no authored confidence ⇒ 0.9 (±ε); helper exists only under `startd8.navigator`

### F-5 — navigator projects the capability-index YAML into Nodes with derived status and typed evidence

- **FRs:** FR-5
- **targetFiles:** `navigator-build`, `src/startd8/navigator/sources_capability.py`
- **dependsOn:** — (no authored dependency)
- **costClass:** llm-integration
- **status:** planned
- **gate (from the FRs' `Verify:`):**
  - FR-5: `startd8 navigator build --source capability-index --format json` exits 0 and JSON contains ≥1 live `capability_id` from the v1.27.0+ manifest

### F-6 — navigator projects a det-req file into FR Nodes with vendor-thin evidence and fr_health without forking the det-req kit

- **FRs:** FR-6
- **targetFiles:** `navigator-build`, `src/startd8/navigator/sources_requirements.py`, `tests/unit/navigator/test_sources_and_cli.py`
- **dependsOn:** — (no authored dependency)
- **costClass:** llm-integration
- **status:** planned
- **gate (from the FRs' `Verify:`):**
  - FR-6: fixture REQ with a commit-anchored code locator builds exit 0 with typed evidence; done-claim without locator ≠ grounded; unit tests pass with det-req-kit **absent** from `sys.path`

### F-7 — the startd8 navigator Typer group exposes build without colliding with the nav app-registry command

- **FRs:** FR-7
- **targetFiles:** `exit-navigator`, `navigator-build`, `src/startd8/cli.py`
- **dependsOn:** — (no authored dependency)
- **costClass:** llm-integration
- **status:** planned
- **gate (from the FRs' `Verify:`):**
  - FR-7: one smoke test — `startd8 navigator --help` lists `build`/`ground`; `startd8 nav --help` still documents the app top-nav registry

### F-8 — the classic app-scaffold wireframe stays byte-identical when no Node fields or profile are present

- **FRs:** FR-8
- **targetFiles:** `src/startd8/wireframe/plan.py`, `tests/unit/wireframe/test_determinism_and_json.py`, `tests/unit/wireframe/test_render_profile.py`
- **dependsOn:** — (no authored dependency)
- **costClass:** llm-integration
- **status:** planned
- **gate (from the FRs' `Verify:`):**
  - FR-8: `test_no_profile_is_byte_identical` + canonical JSON determinism pass without golden edits; classic compose JSON keyset unchanged

### F-9 — a zero-cost navigator ground command enumerates FR and capability keys under a tree and emits dated grounding JSON

- **FRs:** FR-9
- **targetFiles:** `exit-navigator`, `navigator-ground`
- **dependsOn:** — (no authored dependency)
- **costClass:** llm-integration
- **status:** planned
- **gate (from the FRs' `Verify:`):**
  - FR-9: `startd8 navigator ground --root src --out /tmp/ground.json` exits 0; JSON has keys, integer counts, ISO date

### F-10 — the SDK owns nodes_to_wireframe_plan projecting Nodes to a wireframe plan and rendering HTML without ContextCore

- **FRs:** FR-10
- **targetFiles:** `src/startd8/navigator/project.py`, `src/startd8/wireframe_view/`
- **dependsOn:** — (no authored dependency)
- **costClass:** llm-integration
- **status:** planned
- **gate (from the FRs' `Verify:`):**
  - FR-10: unit test builds a plan from two Nodes without importing ContextCore; `html` format writes a file

### F-11 — Navigator offers a Structure-only switch that strips prose to section groups and bare node keys

- **FRs:** FR-11
- **targetFiles:** `src/startd8/wireframe_view/_template.py`, `tests/unit/wireframe/test_render_profile.py`
- **dependsOn:** — (no authored dependency)
- **costClass:** llm-integration
- **status:** planned
- **gate (from the FRs' `Verify:`):**
  - FR-11: a profiled render carries a `structOnly` checkbox + `body.structure-only` CSS + per-item `lbl-key` spans; the no-profile render omits the checkbox and stays byte-identical (`test_no_profile_is_byte_identical`)

### F-12 — Navigator debugging layer offers a top-right view-mode panel with content, structure-only, and combined modes

- **FRs:** FR-12
- **targetFiles:** `src/startd8/wireframe_view/_template.py`, `tests/unit/wireframe/test_render_profile.py`
- **dependsOn:** — (no authored dependency)
- **costClass:** llm-integration
- **status:** planned
- **gate (from the FRs' `Verify:`):**
  - FR-12: a profiled render carries `id="debug"` + `id="combined"` + `body.combined` CSS; Combined shows both `.det` and `.node-meta`; the no-profile render stays byte-identical

### F-13 — Navigator debug panel shows a live provenance/cruft readout from the embedded chrome-provenance summary

- **FRs:** FR-13
- **targetFiles:** `src/startd8/navigator/project.py`, `src/startd8/wireframe_view/_template.py`, `src/startd8/wireframe_view/view.py`, `tests/unit/wireframe/test_render_profile.py`
- **dependsOn:** — (no authored dependency)
- **costClass:** llm-integration
- **status:** planned
- **gate (from the FRs' `Verify:`):**
  - FR-13: a profiled render embeds `payload.chrome` (score/present/total/orphans) and carries the `dbg-prov` readout; the no-profile render stays byte-identical

### F-14 — Navigator debug panel offers a non-destructive Hide-app-scaffold-chrome purge toggle

- **FRs:** FR-14
- **targetFiles:** `src/startd8/wireframe_view/_template.py`, `tests/unit/wireframe/test_render_profile.py`
- **dependsOn:** — (no authored dependency)
- **costClass:** llm-integration
- **status:** planned
- **gate (from the FRs' `Verify:`):**
  - FR-14: a profiled render carries `id="hideScaffold"` + `body.hide-scaffold .signoff` CSS; toggling adds `body.hide-scaffold` and hides `.signoff`/`#signbar`; the no-profile render stays byte-identical

### F-15 — Navigator scaffold mode overlays each template region with its role and data source for adopters

- **FRs:** FR-15
- **targetFiles:** `src/startd8/wireframe_view/_template.py`, `tests/unit/wireframe/test_render_profile.py`
- **dependsOn:** — (no authored dependency)
- **costClass:** llm-integration
- **status:** planned
- **gate (from the FRs' `Verify:`):**
  - FR-15: a profiled render carries `id="scaffold"` + `body.scaffold [data-scaffold]` CSS + ≥6 `data-scaffold` region roles + `data-layer` classifications + a `dbg-layers` legend (layer-aware colouring: control · descriptive · computed · node-driven); toggling adds `body.scaffold`; the no-profile render stays byte-identical

### F-16 — Navigator scaffold-only toggle hides node content and shows just the labelled template skeleton

- **FRs:** FR-16
- **targetFiles:** `src/startd8/wireframe_view/_template.py`, `tests/unit/wireframe/test_render_profile.py`
- **dependsOn:** — (no authored dependency)
- **costClass:** llm-integration
- **status:** planned
- **gate (from the FRs' `Verify:`):**
  - FR-16: a profiled render carries `id="scaffoldOnly"` + `body.scaffold-only` CSS that hides node-layer content; toggling it adds `body.scaffold-only` and `body.scaffold`; each `data-scaffold` region still shows its label; the no-profile render stays byte-identical (`test_no_profile_is_byte_identical`)

### F-17 — Navigator derives the requirements masthead eyebrow, headline, and subtitle from the requirement's own key, H1 title, and DIDL semantic name instead of static profile copy

- **FRs:** FR-17
- **targetFiles:** `src/startd8/navigator/cli_navigator.py`, `src/startd8/navigator/sources_requirements.py`, `tests/unit/navigator/test_sources_and_cli.py`
- **dependsOn:** — (no authored dependency)
- **costClass:** llm-integration
- **status:** planned
- **gate (from the FRs' `Verify:`):**
  - FR-17: `requirements_profile_for(REQ-01)` yields eyebrow `REQ-01`, headline `SDK Node Home`, `summary_meta[0]` = the semantic name; a requirements render's masthead reflects them; `test_no_profile_is_byte_identical` stays green

### F-18 — Navigator derives the requirements section-lead and page title from the requirement's key and H1 title while keeping reading-guidance and vocabulary static

- **FRs:** FR-18
- **targetFiles:** `src/startd8/navigator/sources_requirements.py`, `tests/unit/navigator/test_sources_and_cli.py`
- **dependsOn:** — (no authored dependency)
- **costClass:** llm-integration
- **status:** planned
- **gate (from the FRs' `Verify:`):**
  - FR-18: `requirements_profile_for(REQ-01).section_lead == "What REQ-01 defines"` and `.title == "REQ-01 — SDK Node Home"`; `test_no_profile_is_byte_identical` passes unedited

### F-19 — Navigator groups the top-right control panel under VIEW, OVERLAYS, and TEMPLATE ANATOMY headers by control kind without changing any toggle behaviour

- **FRs:** FR-19
- **targetFiles:** `src/startd8/wireframe_view/_template.py`, `tests/unit/wireframe/test_render_profile.py`
- **dependsOn:** — (no authored dependency)
- **costClass:** llm-integration
- **status:** planned
- **gate (from the FRs' `Verify:`):**
  - FR-19: the profiled render carries three `dbg-group` headers (VIEW/OVERLAYS/TEMPLATE ANATOMY); all five checkbox ids and toggles are unchanged; `test_no_profile_is_byte_identical` passes unedited

## Dependencies (the iteration DAG)

- — no authored `Depends:` edges; iterations are independent by the requirement's declared topology (ordering is the human-gated residue).

## Reuse / phantom audit (§4)

- `src/startd8/navigator/models.py` — ✓ resolves
- `src/startd8/wireframe/plan.py` — ✓ resolves
- `src/startd8/wireframe_view/compose.py` — ✓ resolves
- `src/startd8/wireframe/profile.py` — ✓ resolves
- `tests/unit/navigator/test_models.py` — ✓ resolves
- `src/startd8/navigator/sources_capability.py` — ✓ resolves
- `navigator-build` — ✗ PHANTOM (absent on disk)
- `src/startd8/navigator/sources_requirements.py` — ✓ resolves
- `tests/unit/navigator/test_sources_and_cli.py` — ✓ resolves
- `src/startd8/navigator/det_req.py` — ✓ resolves
- `exit-navigator` — ✗ PHANTOM (absent on disk)
- `src/startd8/cli.py` — ✓ resolves
- `src/startd8/navigator/cli_navigator.py` — ✓ resolves
- `tests/unit/wireframe/test_render_profile.py` — ✓ resolves
- `tests/unit/wireframe/test_determinism_and_json.py` — ✓ resolves
- `navigator-ground` — ✗ PHANTOM (absent on disk)
- `src/startd8/navigator/ground.py` — ✓ resolves
- `src/startd8/navigator/project.py` — ✓ resolves
- `src/startd8/wireframe_view/` — ✓ resolves
- `src/startd8/wireframe_view/_template.py` — ✓ resolves
- `src/startd8/wireframe_view/view.py` — ✓ resolves

## Verify (whole change) — the FR `Verify:` rollup (§5)

- FR-1: `derive_status(has_code_evidence=True, maturity="beta")` returns **`built`**; `maturity="alpha"` (or development/experimental) returns **`thin`**; a field-compat golden (shared field names/types vs a pinned NODE-SCHEMA / frozen fixture — **no** `import contextcore`) passes
- FR-2: (a) navigator Node with typed lives + confidence 0.9 → compose item JSON includes type+ref and confidence; (b) classic app WireframeItem compose JSON gains **no** new keys
- FR-3: ships_when-only + `route_state=declared_unimplemented` absent from `need_items`; app-plan need_items golden unchanged
- FR-4: code+test lives and no authored confidence ⇒ 0.9 (±ε); helper exists only under `startd8.navigator`
- FR-5: `startd8 navigator build --source capability-index --format json` exits 0 and JSON contains ≥1 live `capability_id` from the v1.27.0+ manifest
- FR-6: fixture REQ with a commit-anchored code locator builds exit 0 with typed evidence; done-claim without locator ≠ grounded; unit tests pass with det-req-kit **absent** from `sys.path`
- FR-7: one smoke test — `startd8 navigator --help` lists `build`/`ground`; `startd8 nav --help` still documents the app top-nav registry
- FR-8: `test_no_profile_is_byte_identical` + canonical JSON determinism pass without golden edits; classic compose JSON keyset unchanged
- FR-9: `startd8 navigator ground --root src --out /tmp/ground.json` exits 0; JSON has keys, integer counts, ISO date
- FR-10: unit test builds a plan from two Nodes without importing ContextCore; `html` format writes a file
- FR-11: a profiled render carries a `structOnly` checkbox + `body.structure-only` CSS + per-item `lbl-key` spans; the no-profile render omits the checkbox and stays byte-identical (`test_no_profile_is_byte_identical`)
- FR-12: a profiled render carries `id="debug"` + `id="combined"` + `body.combined` CSS; Combined shows both `.det` and `.node-meta`; the no-profile render stays byte-identical
- FR-13: a profiled render embeds `payload.chrome` (score/present/total/orphans) and carries the `dbg-prov` readout; the no-profile render stays byte-identical
- FR-14: a profiled render carries `id="hideScaffold"` + `body.hide-scaffold .signoff` CSS; toggling adds `body.hide-scaffold` and hides `.signoff`/`#signbar`; the no-profile render stays byte-identical
- FR-15: a profiled render carries `id="scaffold"` + `body.scaffold [data-scaffold]` CSS + ≥6 `data-scaffold` region roles + `data-layer` classifications + a `dbg-layers` legend (layer-aware colouring: control · descriptive · computed · node-driven); toggling adds `body.scaffold`; the no-profile render stays byte-identical
- FR-16: a profiled render carries `id="scaffoldOnly"` + `body.scaffold-only` CSS that hides node-layer content; toggling it adds `body.scaffold-only` and `body.scaffold`; each `data-scaffold` region still shows its label; the no-profile render stays byte-identical (`test_no_profile_is_byte_identical`)
- FR-17: `requirements_profile_for(REQ-01)` yields eyebrow `REQ-01`, headline `SDK Node Home`, `summary_meta[0]` = the semantic name; a requirements render's masthead reflects them; `test_no_profile_is_byte_identical` stays green
- FR-18: `requirements_profile_for(REQ-01).section_lead == "What REQ-01 defines"` and `.title == "REQ-01 — SDK Node Home"`; `test_no_profile_is_byte_identical` passes unedited
- FR-19: the profiled render carries three `dbg-group` headers (VIEW/OVERLAYS/TEMPLATE ANATOMY); all five checkbox ids and toggles are unchanged; `test_no_profile_is_byte_identical` passes unedited

_det-plan/0.1 — projected `$0` from the paired det-req; maturity `0.1` (un-hardened). The projector owns the format's derived fields; the ordering strategy is the human-gated residue._
