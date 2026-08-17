<!-- GENERATED det-plan/0.1 — projected $0 from the paired det-req by startd8 plan_codegen; do not edit by hand -->

# SDK navigator models each pipeline stage as a Node, promotes a requirement's `Verify:` clause to a checkable acceptance oracle, and traces a delivered artifact back through the stages to the originating requirement — the prose→product compiler made observable end to end. — Implementation Plan (det-plan/0.1)

- **version:** 0.1
- **formatVersion:** det-plan/0.1
- **pairsWith:** `REQ-08-nl-programming-pipeline-provenance.md`
- **companionKind:** PLAN
- **maturity:** 0.1
- **handle:** `plan/sdk-navigator-models-each-pipeline-stage-as-a-558d6fc7`
- **ref:** `cc:intent:requirements-visualization:plan:req-08`

> A **det-plan is a `$0` projection of a det-req** — this document is derived, never authored. Its FR grouping and ordering are the requirement's authored structure; the strategic build-ordering strategy is the human's to add (the human-gated residue).

## Iterations

_9 iteration(s); costClass rollup: 9 llm-integration._

### F-1 — SDK navigator projects each prose-to-product pipeline stage as a Node using category plus attributes without changing the Node model

- **FRs:** FR-1
- **targetFiles:** `src/startd8/navigator/sources_pipeline.py`, `src/startd8/navigator/view_definition.py`
- **dependsOn:** — (no authored dependency)
- **costClass:** llm-integration
- **status:** planned
- **gate (from the FRs' `Verify:`):**
  - FR-1: `node_field_names()` is unchanged AND `nodes_from_pipeline()` returns six nodes each with `category=="pipeline-stage"` and a string `ordinal` attribute (the `attributes` bag is `Dict[str,str]`) whose value parses as an int in 0..5, the six ordinals forming the set {0,1,2,3,4,5}, each stage `status ∈ {built, spec}`, AND `PIPELINE_PROFILE.statuses` keys cover every status `nodes_from_pipeline()` emits

### F-2 — Navigator wires stage dependency edges via existing child_keys so the pipeline renders as an ordered DAG

- **FRs:** FR-2
- **targetFiles:** `src/startd8/navigator/sources_pipeline.py`
- **dependsOn:** — (no authored dependency)
- **costClass:** llm-integration
- **status:** planned
- **gate (from the FRs' `Verify:`):**
  - FR-2: `stage:contract` lists `stage:functional` in `child_keys`, `stage:impl`/`stage:test`/`stage:doc` each list `stage:contract`, every referenced key is an emitted stage key, and `topo_order()` (a topological sort of the stage graph, **called by `nodes_from_pipeline` as a fail-loud build-time acyclicity guard** — R8-EB-3) succeeds (raising `graphlib.CycleError` on a cycle) yielding an order consistent with the FR-1 ordinals

### F-3 — Navigator CLI exposes a pipeline source that renders the six stages through the existing renderers

- **FRs:** FR-3
- **targetFiles:** `src/startd8/navigator/cli_navigator.py`, `src/startd8/navigator/sources_pipeline.py`
- **dependsOn:** — (no authored dependency)
- **costClass:** llm-integration
- **status:** planned
- **gate (from the FRs' `Verify:`):**
  - FR-3: `startd8 navigator build --source pipeline --format json` exits 0 with six nodes; `--source requirements|capability-index|node-schema|nodes-json` behave unchanged

### F-4 — SDK navigator parses each requirement Verify-clause into a typed acceptance-oracle descriptor extracting the single runnable command span and classifying command assertion or manual

- **FRs:** FR-4
- **targetFiles:** `src/startd8/navigator/verify_oracle.py`
- **dependsOn:** — (no authored dependency)
- **costClass:** llm-integration
- **status:** planned
- **gate (from the FRs' `Verify:`):**
  - FR-4: for a fixture doc each FR yields a descriptor with `kind in {command,assertion,manual}`; a single-command mixed clause (backtick `startd8 …` + prose assertion) yields `kind=command` with `command_argv` set and the prose retained in `assertion_text`; a two-command or `;`-joined clause is `manual` (reason multi-command); a prose-only or closed-set-placeholder clause is `assertion`/`manual`, never `command`

### F-5 — Navigator verify command reports a per-requirement pass-fail-skip verdict defaulting inert and executing read-only allow-listed command oracles only under an explicit opt-in flag

- **FRs:** FR-5
- **targetFiles:** `src/startd8/navigator/cli_navigator.py`, `src/startd8/navigator/verify_oracle.py`
- **dependsOn:** — (no authored dependency)
- **costClass:** llm-integration
- **status:** planned
- **gate (from the FRs' `Verify:`):**
  - FR-5: `startd8 navigator verify --requirements <doc>` exits 0 emitting only `skip` verdicts with no subprocess spawned; `--run-oracle` runs read-only allow-listed navigator commands via argv (never `shell=True`) reporting pass=rc0/fail=rc≠0, a `startd8 generate …` / `--out` / non-`startd8` command stays `skip`, a timeout yields `fail` reason "timeout", a missing input yields `error`; exit code is 0 when no verdict is `fail`/`error` and non-zero iff any `fail`/`error`, so CI can gate on the process rc

### F-6 — SDK navigator extends provenance to trace a delivered artifact back through the pipeline stages to its originating requirement

- **FRs:** FR-6
- **targetFiles:** `src/startd8/navigator/provenance.py`, `src/startd8/navigator/sources_pipeline.py`
- **dependsOn:** — (no authored dependency)
- **costClass:** llm-integration
- **status:** planned
- **gate (from the FRs' `Verify:`):**
  - FR-6: `pipeline_provenance` lives in `provenance.py` next to `chrome_provenance`, emits rows with keys `{element,stage,origin,value,present}`, resolves an artifact to its owning stage by **longest-prefix** `sdk_artifact` match (R1-S8), resolves an FR-id `query` via `requirement_nodes` to the FR's code file, emits a single `present=False` row for an artifact owned by no stage (or an unresolvable FR-id), still emits a row for a SPEC (un-built) stage the chain passes through (R1-S10), and for an FR with a code `Lives:` ref returns an ordered chain whose stages are a subsequence of the FR-1 stage ordinals ending at the requirement

### F-7 — Navigator renders oracle verdicts and the pipeline-provenance chain through the existing renderers without a new HTML shell

- **FRs:** FR-7
- **targetFiles:** `src/startd8/navigator/cli_navigator.py`, `src/startd8/navigator/sources_pipeline.py`
- **dependsOn:** — (no authored dependency)
- **costClass:** llm-integration
- **status:** planned
- **gate (from the FRs' `Verify:`):**
  - FR-7: `startd8 navigator verify --requirements <doc> --format json` emits a per-FR verdict array; `--source pipeline --renderer tree` renders stage nodes whose `artifact_chain` attribute appears as meta rows, and `--renderer graph` renders the stage DAG

### F-8 — The pipeline source and oracle and provenance extension leave Node and the app-scaffold path byte-identical

- **FRs:** FR-8
- **targetFiles:** `src/startd8/navigator/sources_pipeline.py`, `tests/unit/navigator/test_pipeline_source.py`, `tests/unit/wireframe/test_render_profile.py`
- **dependsOn:** — (no authored dependency)
- **costClass:** llm-integration
- **status:** planned
- **gate (from the FRs' `Verify:`):**
  - FR-8: four one-condition guards — G1 byte-identity + field-compat: `test_no_profile_is_byte_identical` (in `test_render_profile.py`) and `test_no_node_field_added_by_pipeline_source` pass unedited; G2 registry governance: `test_validate_definitions_clean_with_pipeline_domain` (`validate_definitions(DEFINITION_REGISTRY)` returns no issues with the `pipeline` domain present); G3 status-vocab well-formedness (a DEDICATED assertion, not `validate_definitions` — R1-F3): `test_pipeline_status_vocab_is_wellformed` (each `PIPELINE_PROFILE.status` has non-empty `label`/`meaning`/`color` + int `severity`); G4 no new shell: `test_no_new_module_imports_wireframe_view_for_pipeline_path`

### F-9 — SDK navigator exposes a provenance command that traces an FR-id or path through the pipeline and renders the chain as json or an html tree

- **FRs:** FR-9
- **targetFiles:** `src/startd8/navigator/cli_navigator.py`, `src/startd8/navigator/provenance.py`
- **dependsOn:** — (no authored dependency)
- **costClass:** llm-integration
- **status:** planned
- **gate (from the FRs' `Verify:`):**
  - FR-9: `startd8 navigator provenance --query FR-1 --requirements <doc>` exits 0 with a chain reaching the owning stage; `--query <unowned-path>` exits 1 emitting a single not-found row; `--query FR-1` without `--requirements` exits non-zero naming `--requirements`; `--format html --out <p>` writes an HTML tree whose nodes carry the chain (category `pipeline-provenance`) and the app-scaffold path stays byte-identical

## Dependencies (the iteration DAG)

- — no authored `Depends:` edges; iterations are independent by the requirement's declared topology (ordering is the human-gated residue).

## Reuse / phantom audit (§4)

- `src/startd8/navigator/sources_pipeline.py` — ✓ resolves
- `src/startd8/navigator/view_definition.py` — ✓ resolves
- `src/startd8/navigator/cli_navigator.py` — ✓ resolves
- `src/startd8/navigator/verify_oracle.py` — ✓ resolves
- `src/startd8/navigator/provenance.py` — ✓ resolves
- `tests/unit/navigator/test_pipeline_source.py` — ✓ resolves
- `tests/unit/wireframe/test_render_profile.py` — ✓ resolves
- `src/startd8/navigator/sources_pipeline.py, test tests/unit/navigator/test_pipeline_source.py, test tests/unit/wireframe/test_render_profile.py` — ✗ PHANTOM (absent on disk)

## Verify (whole change) — the FR `Verify:` rollup (§5)

- FR-1: `node_field_names()` is unchanged AND `nodes_from_pipeline()` returns six nodes each with `category=="pipeline-stage"` and a string `ordinal` attribute (the `attributes` bag is `Dict[str,str]`) whose value parses as an int in 0..5, the six ordinals forming the set {0,1,2,3,4,5}, each stage `status ∈ {built, spec}`, AND `PIPELINE_PROFILE.statuses` keys cover every status `nodes_from_pipeline()` emits
- FR-2: `stage:contract` lists `stage:functional` in `child_keys`, `stage:impl`/`stage:test`/`stage:doc` each list `stage:contract`, every referenced key is an emitted stage key, and `topo_order()` (a topological sort of the stage graph, **called by `nodes_from_pipeline` as a fail-loud build-time acyclicity guard** — R8-EB-3) succeeds (raising `graphlib.CycleError` on a cycle) yielding an order consistent with the FR-1 ordinals
- FR-3: `startd8 navigator build --source pipeline --format json` exits 0 with six nodes; `--source requirements|capability-index|node-schema|nodes-json` behave unchanged
- FR-4: for a fixture doc each FR yields a descriptor with `kind in {command,assertion,manual}`; a single-command mixed clause (backtick `startd8 …` + prose assertion) yields `kind=command` with `command_argv` set and the prose retained in `assertion_text`; a two-command or `;`-joined clause is `manual` (reason multi-command); a prose-only or closed-set-placeholder clause is `assertion`/`manual`, never `command`
- FR-5: `startd8 navigator verify --requirements <doc>` exits 0 emitting only `skip` verdicts with no subprocess spawned; `--run-oracle` runs read-only allow-listed navigator commands via argv (never `shell=True`) reporting pass=rc0/fail=rc≠0, a `startd8 generate …` / `--out` / non-`startd8` command stays `skip`, a timeout yields `fail` reason "timeout", a missing input yields `error`; exit code is 0 when no verdict is `fail`/`error` and non-zero iff any `fail`/`error`, so CI can gate on the process rc
- FR-6: `pipeline_provenance` lives in `provenance.py` next to `chrome_provenance`, emits rows with keys `{element,stage,origin,value,present}`, resolves an artifact to its owning stage by **longest-prefix** `sdk_artifact` match (R1-S8), resolves an FR-id `query` via `requirement_nodes` to the FR's code file, emits a single `present=False` row for an artifact owned by no stage (or an unresolvable FR-id), still emits a row for a SPEC (un-built) stage the chain passes through (R1-S10), and for an FR with a code `Lives:` ref returns an ordered chain whose stages are a subsequence of the FR-1 stage ordinals ending at the requirement
- FR-7: `startd8 navigator verify --requirements <doc> --format json` emits a per-FR verdict array; `--source pipeline --renderer tree` renders stage nodes whose `artifact_chain` attribute appears as meta rows, and `--renderer graph` renders the stage DAG
- FR-8: four one-condition guards — G1 byte-identity + field-compat: `test_no_profile_is_byte_identical` (in `test_render_profile.py`) and `test_no_node_field_added_by_pipeline_source` pass unedited; G2 registry governance: `test_validate_definitions_clean_with_pipeline_domain` (`validate_definitions(DEFINITION_REGISTRY)` returns no issues with the `pipeline` domain present); G3 status-vocab well-formedness (a DEDICATED assertion, not `validate_definitions` — R1-F3): `test_pipeline_status_vocab_is_wellformed` (each `PIPELINE_PROFILE.status` has non-empty `label`/`meaning`/`color` + int `severity`); G4 no new shell: `test_no_new_module_imports_wireframe_view_for_pipeline_path`
- FR-9: `startd8 navigator provenance --query FR-1 --requirements <doc>` exits 0 with a chain reaching the owning stage; `--query <unowned-path>` exits 1 emitting a single not-found row; `--query FR-1` without `--requirements` exits non-zero naming `--requirements`; `--format html --out <p>` writes an HTML tree whose nodes carry the chain (category `pipeline-provenance`) and the app-scaffold path stays byte-identical

_det-plan/0.1 — projected `$0` from the paired det-req; maturity `0.1` (un-hardened). The projector owns the format's derived fields; the ordering strategy is the human-gated residue._
