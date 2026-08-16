# Natural-Language Programming Pipeline & End-to-End Provenance — Requirements

**Project:** startd8-sdk   **Criticality:** high
**Version:** 0.1   **Date:** 2026-08-15
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** the source thesis `~/Documents/craft/THE_NATURAL_LANGUAGE_PROGRAMMING_SYSTEM.md` (a `/reflective-analogy` instance)
**Inherits standards:** NODE-SCHEMA · NAMING_CONVENTION · REQ-01 (SDK Node home) · REQ-02 (N-level tree renderer) · REQ-03 (a11y renderer + corpus index) · REQ-04 (lift lenses to shared transform) · REQ-05 (graph/network topology renderer) · REQ-06 (corpus governance) · REQ-07 (diff audience)
**Audience:** operator / adopter
**Trust boundary:** local filesystem + authored req/plan docs + read-only repo; no network fetch; the `Verify:`-oracle path runs authored acceptance checks and MUST default to inert (no execution unless explicitly opted in — see FR-4 / Risks)
**Data classification:** internal

> **Readable handle:** `feature/sdk-navigator-models-each-pipeline-stage-as-a-558d6fc7`
> **Semantic name:** *SDK navigator models each pipeline stage as a Node, promotes a requirement's `Verify:` clause to a checkable acceptance oracle, and traces a delivered artifact back through the stages to the originating requirement — the prose→product compiler made observable end to end.*
> **Canonical ref:** `cc:intent:requirements-visualization:feature:req-08`

---

## 0. Why this exists — the pipeline made observable (Mieruka)

The source thesis (`THE_NATURAL_LANGUAGE_PROGRAMMING_SYSTEM.md`) names the SDK's existing machinery as
a **compiler whose source language is prose**: functional description (det-req FRs, the *source
language*) → contract / Node (the *IR*) → implementation (two back-ends: the deterministic $0 cascade =
compiler, the LLM-driven path = interpreter) → tests derived from `Verify:` (the *oracle*) → docs (the
*man-page*). The essential residue is the two human bookends — DATA MODEL at the front, RETROSPECTIVE
at the back; everything between is *accident* the machine carries.

That thesis is a lens on architecture the SDK already ships. This spec extracts **only the concrete,
repo-able artifacts** it shakes out, and homes them in the **navigator** — the front-end review console
for the DATA MODEL bookend. It is a **modeling / visualization** concern, not a re-implementation of
the pipeline. Three deliverables, each grounded to a verifiable navigator change:

1. **A `Stage` node type** — model each pipeline stage (intent · functional · contract · impl · test ·
   doc) as a `Node`, so any project can be *viewed* as a compilation without redesigning `Node`.
2. **`Verify:`-as-oracle** — the det-req `Verify:` clause (today parsed as prose in `det_req.py`) is
   already the one essential test artifact. Promote it from displayed text to a **checkable acceptance
   oracle**: parse it, classify it, and (opt-in) evaluate command-shaped clauses to report pass/fail.
3. **End-to-end pipeline provenance** — **extend** `provenance.py` (which today audits *chrome*
   origins) with an artifact→stage→requirement trace, so a delivered file is traceable back through the
   stages to the FR — and a `Verify:` failure is attributable to a stage.

The philosophy lives in this Overview. The FRs below stay welded to concrete navigator behavior.

## How a `Stage` fits `Node` without forking (Kagami: extend, don't fork)

A `Stage` is **not** a new dataclass and adds **no field to `Node`**. It is a `Node` instance in a
reserved category with typed attributes and existing hierarchy fields:

- `category = "pipeline-stage"` — the sole discriminator (mirrors how `sources_requirements` uses
  `category="functional-requirements"` and `sources_node_schema` groups by curated axis).
- `key` — the stage id (`stage:intent`, `stage:functional`, `stage:contract`, `stage:impl`,
  `stage:test`, `stage:doc`); `does` — the transform prose ("prose → structured requirements").
- `attributes` (the open `Dict[str, str]` bag, already the extension seam) carries the stage-specific
  typing: `kind="stage"`, `ordinal` (0–5), `human_form`, `sdk_artifact`, `compiler_analogue`,
  `essence` (`essential|accidental`). No schema change — this is exactly the `_FIELD_META`-style
  curated-annotation-over-structural-truth pattern REQ already uses.
- `child_keys` — the existing DEPENDS-ON edge — links a stage to the stage(s) it consumes and to the
  FR/artifact nodes flowing through it. `status`/`confidence` derive from real evidence via the
  existing `derive_status` / `default_confidence`, unchanged.

So `Stage` is a **projection convention over `Node`**, homed in a new `sources_pipeline.py` (sibling of
`sources_requirements.py` / `sources_node_schema.py`) with its own `RenderProfile` — identical in shape
to every other source. The field-compat golden (`node_field_names()`) stays green because `Node` is
untouched.

## Overview

Add a **pipeline source** to the navigator that projects the six named stages of the prose→product
compiler as `Node`s (reusing the existing source→profile→render seam), promote the authored `Verify:`
clause to a first-class **acceptance oracle** (parse → classify → opt-in evaluate → pass/fail), and
extend the existing `chrome_provenance` audit with a **pipeline provenance** trace that walks a
delivered artifact back through the stages to its originating requirement. All three surface through the
existing `startd8 navigator` CLI and the existing renderers (tree / a11y / graph). Nothing here
re-implements plan-ingestion or the prime-contractor — it **models** them.

## Objectives

- **O-1:** Project the prose→product pipeline as `Node`s (six stages, DEPENDS-ON edges) via a new
  `--source pipeline`, renderable by the existing tree/a11y/graph renderers — target: `startd8
  navigator build --source pipeline --format json` exits 0 and emits six stage nodes.
- **O-2:** Promote a requirement's `Verify:` clause to a checkable **acceptance oracle** — parse +
  classify every FR's `Verify:` (command-shaped vs prose-assertion vs manual), and (opt-in) evaluate
  the command-shaped ones to report per-FR pass/fail — target: a `verify` command emits a pass/fail/
  skip verdict per FR without mutating the repo.
- **O-3:** Trace a delivered artifact **back through the stages to the originating requirement** by
  extending `provenance.py` — target: given an FR (or a `Touches`/`Lives` file), emit an ordered
  artifact→stage→requirement chain the navigator can render.
- **O-4:** The pipeline source, oracle, and provenance trace are **standalone / additive** — the
  app-scaffold wireframe path and `Node` stay byte-identical; the field-compat golden passes unedited.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| scope-creep | Sliding from *modeling* the pipeline into *re-implementing* a pipeline engine (a stage executor / orchestrator) | Hard non-goal (NR-1/NR-2): stages are **projected Nodes**, the oracle **reads authored `Verify:`** — no stage runs codegen, no orchestration; every FR touches only `src/startd8/navigator/` | high |
| security | The `Verify:`-oracle evaluating an authored clause = arbitrary command execution on a review machine | **Default inert**: parse+classify only; execution is opt-in (`--run-oracle`), off by default, no shell string interpolation (argv list), no network, honors the stated trust boundary; prose/manual clauses are never executed | high |
| quality | `Stage` bloating `Node` (a new field / dataclass = a fork) | Kagami: **no** `Node` change — `category="pipeline-stage"` + `attributes` bag only; guard with the existing `node_field_names()` field-compat golden | high |
| quality | Re-inventing provenance instead of extending `chrome_provenance` (Mottainai) | The pipeline-provenance FR **extends** `provenance.py` (same element→origin→value shape), does not add a parallel module | medium |
| quality | Oracle mis-classifying a prose `Verify:` as a command and "failing" it | Conservative classifier: only clauses matching an explicit command grammar (backtick/`$`-prefixed / `startd8 …`) are runnable; everything else is `manual` (never fail, surfaced as needs-human) | medium |

## Functional requirements

- **FR-1 — `Stage` node projection (extend Node, don't fork).** Add `src/startd8/navigator/sources_pipeline.py` projecting the six prose→product stages (intent · functional · contract · impl · test · doc) as `Node`s with `category="pipeline-stage"` and typed `attributes` (ordinal · human_form · sdk_artifact · compiler_analogue · essence), adding **no** field to `Node`. Name: SDK navigator projects each prose-to-product pipeline stage as a Node using category plus attributes without changing the Node model. Touches: src/startd8/navigator/sources_pipeline.py, src/startd8/navigator/models.py. Lives: doc ~/Documents/craft/THE_NATURAL_LANGUAGE_PROGRAMMING_SYSTEM.md. Approve?: is Stage a projection over Node (category + attributes) with zero Node field changes?. Verify: `node_field_names()` is unchanged AND `nodes_from_pipeline()` returns six nodes each with `category=="pipeline-stage"` and a string `ordinal` attribute (the `attributes` bag is `Dict[str,str]`) whose value parses as an int in 0..5, the six ordinals forming the set {0,1,2,3,4,5}. Serves: O-1
- **FR-2 — Stage DEPENDS-ON edges.** Each stage Node carries `child_keys` linking it to the stage(s) it consumes (functional←intent, contract←functional, impl←contract, test←contract, doc←contract) so the pipeline renders as an ordered DAG, reusing the existing DEPENDS-ON `child_keys` field. Name: Navigator wires stage dependency edges via existing child_keys so the pipeline renders as an ordered DAG. Touches: src/startd8/navigator/sources_pipeline.py. Lives: code src/startd8/navigator/sources_pipeline.py. Approve?: do stage edges use child_keys only (no new edge field)?. Verify: `stage:contract` lists `stage:functional` in `child_keys`, `stage:impl`/`stage:test`/`stage:doc` each list `stage:contract`, every referenced key is an emitted stage key, and a topological sort of the stage graph succeeds (no cycle) yielding an order consistent with the FR-1 ordinals. Serves: O-1
- **FR-3 — `--source pipeline` CLI seam.** Extend `cli_navigator.build` with `--source pipeline` (routing to `nodes_from_pipeline()` + a `PIPELINE_PROFILE`), renderable by the existing `--format json|html|a11y` and `--renderer tree|graph`, additive with no break to existing sources. Name: Navigator CLI exposes a pipeline source that renders the six stages through the existing renderers. Touches: src/startd8/navigator/cli_navigator.py, src/startd8/navigator/sources_pipeline.py. Lives: code src/startd8/navigator/cli_navigator.py. Approve?: is `--source pipeline` additive (existing sources/formats unchanged)?. Verify: `startd8 navigator build --source pipeline --format json` exits 0 with six nodes; `--source requirements|capability-index|node-schema|nodes-json` behave unchanged. Serves: O-1
- **FR-4 — Verify-as-oracle: parse + classify.** Add a `verify_oracle` module that reads a det-req doc's parsed FRs (via `det_req.parse_fr_lines_prefer_kit`) and classifies each authored Verify-clause into `command` (an explicit runnable command grammar — backtick / `$`-prefixed / `startd8 …`), `assertion` (a prose acceptance statement), or `manual` (needs a human) — producing a typed per-FR oracle descriptor, no execution. Name: SDK navigator parses each requirement Verify-clause into a typed acceptance-oracle descriptor classified command assertion or manual. Touches: src/startd8/navigator/verify_oracle.py. Lives: code src/startd8/navigator/verify_oracle.py. Approve?: does the classifier only mark explicitly command-shaped clauses runnable (everything else manual/assertion), reading FRs via the existing det_req.parse_fr_lines_prefer_kit without modifying det_req.py?. Verify: for a fixture doc each FR yields a descriptor with `kind in {command,assertion,manual}` and a prose-only acceptance clause classifies as `assertion`/`manual`, never `command`. Serves: O-2
- **FR-5 — `Verify:`-as-oracle: opt-in evaluate + pass/fail.** Add `startd8 navigator verify --requirements <doc>` that reports a per-FR verdict (`pass|fail|skip`): by default it evaluates nothing (inert — every `command` clause reports `skip`, every `manual` reports `skip`), and only with `--run-oracle` does it execute `command`-kind clauses (argv list, no shell interpolation, no network, read-only cwd) to yield real `pass|fail`. Name: Navigator verify command reports a per-requirement pass-fail-skip verdict defaulting inert and executing command oracles only under an explicit opt-in flag. Touches: src/startd8/navigator/cli_navigator.py, src/startd8/navigator/verify_oracle.py. Lives: code src/startd8/navigator/verify_oracle.py. Approve?: is oracle execution off by default and safe (argv/no-shell/no-network) under `--run-oracle`?. Verify: `startd8 navigator verify --requirements <doc>` exits 0 emitting only `skip` verdicts with no subprocess spawned; `--run-oracle` runs command-kind clauses via argv (never `shell=True`) and reports pass/fail; exit code is 0 when no verdict is `fail` (all-`skip` inert runs included) and non-zero iff at least one `fail` is present, so CI can gate on the process rc. Serves: O-2
- **FR-6 — Pipeline provenance trace (extend provenance.py).** Add `pipeline_provenance(nodes, stages)` alongside `chrome_provenance` in `src/startd8/navigator/provenance.py` returning, for a given FR (or a `Touches`/`Lives` file), the ordered artifact→stage→requirement chain (each row: `element` · `stage` · `origin` · `present`), reusing the existing element→origin→value row shape — extending, not replacing, `chrome_provenance`. Name: SDK navigator extends provenance to trace a delivered artifact back through the pipeline stages to its originating requirement. Touches: src/startd8/navigator/provenance.py, src/startd8/navigator/sources_pipeline.py. Lives: code src/startd8/navigator/provenance.py. Approve?: does pipeline provenance extend provenance.py (same row shape) rather than add a parallel module?. Verify: `pipeline_provenance` lives in `provenance.py` next to `chrome_provenance`, and for an FR with a code `Lives:` ref returns an ordered chain whose stages are a subsequence of the FR-1 stage ordinals ending at the requirement. Serves: O-3
- **FR-7 — `verify`/provenance render surface.** Surface the oracle verdicts and the pipeline-provenance chain through the existing renderers: the `verify` command supports `--format json|html`, and pipeline provenance is renderable as Nodes (stage nodes annotated with their downstream artifact chain) via the existing tree/graph renderer — no new HTML shell. Name: Navigator renders oracle verdicts and the pipeline-provenance chain through the existing renderers without a new HTML shell. Touches: src/startd8/navigator/cli_navigator.py, src/startd8/navigator/sources_pipeline.py. Lives: code src/startd8/navigator/cli_navigator.py. Approve?: do verdicts + provenance reuse the existing renderers (no bespoke shell)?. Verify: `startd8 navigator verify --requirements <doc> --format json` emits a per-FR verdict array; `--source pipeline --renderer graph` renders stage nodes with their artifact-chain annotations. Serves: O-2, O-3
- **FR-8 — Byte-identity + field-compat guard.** The pipeline source, oracle, and provenance extension are standalone/additive: `Node` is unchanged, the app-scaffold wireframe path is byte-identical, and the field-compat golden passes unedited. Name: The pipeline source and oracle and provenance extension leave Node and the app-scaffold path byte-identical. Touches: tests/unit/navigator/test_pipeline_source.py, tests/unit/wireframe/test_render_profile.py. Lives: test tests/unit/wireframe/test_render_profile.py. Approve?: is Node/app-scaffold untouched by this REQ?. Verify: `node_field_names()` golden + `test_no_profile_is_byte_identical` pass unedited; no new module imports `wireframe_view` for the pipeline/oracle path. Serves: O-4

## Non-goals

- **NR-1:** Does **NOT** re-implement plan-ingestion or the prime-contractor — it **models** them as
  projected `Stage` Nodes. No stage node runs codegen, LLM calls, or orchestration; the two generation
  paths keep their existing homes (`backend_codegen/`, `contractors/`).
- **NR-2:** Does **NOT** add a pipeline execution / stage-runner engine. The `Verify:`-oracle evaluates
  *authored acceptance clauses only* (opt-in), it does not drive the compiler pipeline.
- **NR-3:** Does **NOT** add or change any `Node` field / dataclass — `Stage` is `category` +
  `attributes` only (guarded by the field-compat golden).
- **NR-4:** Does **NOT** author documentation content (stage 5 / bucket 4) — it only *models* the doc
  stage as a Node; real content stays with the user/company (CLAUDE.md bucket separation).
- **NR-5:** Does **NOT** derive tests from `Verify:` (the `test_emitter` path). The oracle *checks* an
  authored `Verify:`, it does not *generate* a test suite.
- **NR-6:** Does **NOT** introduce a new CSS/HTML shell — reuses the tree / a11y / graph renderers
  (REQ-02 / REQ-03 / REQ-05).

## Contract projection

- **Backend:** python-cli-surface
- **Vocabulary home (cite):** `~/Documents/craft/THE_NATURAL_LANGUAGE_PROGRAMMING_SYSTEM.md` · `dev-os/NODE-SCHEMA.md` · `docs/NAMING_CONVENTION.md`

| Entry (name) | Kind | Words/Structure | Notes |
|--------------|------|-----------------|-------|
| navigator-build | command | structure | existing; gains `--source pipeline` |
| source-pipeline | option | structure | `--source pipeline` (six stage Nodes) |
| navigator-verify | command | structure | new: `startd8 navigator verify --requirements … [--run-oracle] [--format json\|html]` |
| run-oracle | option | structure | `--run-oracle` (opt-in, default OFF — argv/no-shell/no-network execution) |

Library seams (Touches file paths): `src/startd8/navigator/sources_pipeline.py`,
`src/startd8/navigator/verify_oracle.py`, `src/startd8/navigator/provenance.py`,
`src/startd8/navigator/cli_navigator.py`, `src/startd8/navigator/models.py`.
Read-only imports (not edited): `src/startd8/navigator/det_req.py`
(`parse_fr_lines_prefer_kit` — consumed by the oracle, unchanged).

## Appendix A — Accepted (with where merged)
## Appendix B — Rejected (with rationale)
## Appendix C — Incoming review rounds

*v0.1 — extracts the three repo-able artifacts of the Natural-Language Programming System thesis
(`Stage` node type · `Verify:`-as-oracle · end-to-end pipeline provenance) as additive navigator
changes. Philosophy in the Overview; FRs grounded to verifiable navigator behavior. Ready for CRP.*
*v0.1.1 — pre-CRP grounding fixes: FR-1 `ordinal` typed as string-parseable-int (bag is `Dict[str,str]`);
FR-2 Verify asserts a real topological sort (not just subset); FR-4 `Touches` narrowed to `verify_oracle.py`
(det_req.py is a read-only import); FR-5 defines aggregate exit-code semantics for CI gating.*
