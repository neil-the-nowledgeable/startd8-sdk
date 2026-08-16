# Natural-Language Programming Pipeline & End-to-End Provenance — Requirements

**Project:** startd8-sdk   **Criticality:** high
**Version:** 0.2 (Post-planning — self-reflective update)   **Date:** 2026-08-15
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** `PLAN-nl-programming-pipeline-provenance.md` · the source thesis `~/Documents/craft/THE_NATURAL_LANGUAGE_PROGRAMMING_SYSTEM.md` (a `/reflective-analogy` instance)
**Inherits standards:** NODE-SCHEMA · NAMING_CONVENTION · REQ-01 (SDK Node home) · REQ-02 (N-level tree renderer) · REQ-03 (a11y renderer + corpus index) · REQ-04 (lift lenses to shared transform) · REQ-05 (graph/network topology renderer) · REQ-06 (corpus governance) · REQ-07 (diff audience)
**Audience:** operator / adopter
**Trust boundary:** local filesystem + authored req/plan docs + read-only repo; no network fetch; the `Verify:`-oracle path runs authored acceptance checks and MUST default to inert (no execution unless explicitly opted in — see FR-4 / Risks)
**Data classification:** internal

> **Readable handle:** `feature/sdk-navigator-models-each-pipeline-stage-as-a-558d6fc7`
> **Semantic name:** *SDK navigator models each pipeline stage as a Node, promotes a requirement's `Verify:` clause to a checkable acceptance oracle, and traces a delivered artifact back through the stages to the originating requirement — the prose→product compiler made observable end to end.*
> **Canonical ref:** `cc:intent:requirements-visualization:feature:req-08`

---

## 0. Planning Insights (Self-Reflective Update)

> This section documents what changed between v0.1 (pre-planning) and v0.2 (post-planning). The
> planning pass (`PLAN-nl-programming-pipeline-provenance.md`) mapped every FR to real `navigator/`
> seams and revealed six corrections — mostly refinements, but two (D-1, D-3) would have bitten
> during coding. The spec was well-grounded structurally; planning tested the *mechanics*.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| **D-1** — FR-1/FR-3 hand-build a `PIPELINE_PROFILE` `RenderProfile`. | All 3 real domains build the profile as a `ViewDefinition(extends="base", vocabulary, chrome)` in `DEFINITION_REGISTRY` (`view_definition.py:377-415`), projected via `to_render_profile`. | FR-1/FR-3 now Touch `view_definition.py` and add a `pipeline` domain definition + registry entry; the pipeline source inherits base theme/lenses and the `view-definition --validate` governance for free. |
| **D-2** — a stage Node is just `category` + `attributes`. | node-schema grounds each field via a real `code` Lives (`models.py`); stages should ground the same way — the `sdk_artifact` path resolving on disk → BUILT via `derive_status`. Needs a status **vocabulary** in the pipeline def. | FR-1: stage `status` derives from its `sdk_artifact` resolving on disk; the pipeline `ViewDefinition` declares a built/spec status vocabulary. |
| **D-3** — a `Verify:` clause is atomically one of `command`/`assertion`/`manual`. | Real clauses (incl. REQ-08's own) **mix** a backtick command with a prose assertion (`\`startd8 … build\` exits 0 with six nodes`); an argv exec can only check the command's **exit code**, not the assertion. | FR-4 now *extracts* the runnable span (+ placeholder and verb guards); FR-5 defines `pass` = extracted command exit 0, with the prose assertion emitted as the human-checkable residue (not machine-asserted). |
| **D-4** — `pipeline_provenance` reuses the *same* `element→origin→value` row shape. | `chrome_provenance` rows are `{element,origin,value,present}` with signature `(nodes,plan,profile)`; the pipeline trace is a **sibling** `{element,stage,origin,value,present}` with `(nodes,stages)` — same module/idea, not shape-identical. | FR-6 restated: a sibling row schema (adds `stage`, keeps `value`) *in* `provenance.py`, extending the module, not claiming shape-identity. |
| **D-5** — pipeline provenance is "renderable as Nodes". | The trace returns **rows**, not Nodes; to render it must be folded onto stage-Node `attributes` (which `render_tree.py:151` surfaces as meta rows). The graph renderer reads attributes for href only — so the chain surfaces in *tree*, not graph. | FR-7: annotate stage Nodes via `attributes["artifact_chain"]`; the chain is a tree affordance, the graph shows the stage DAG. |
| **D-6** — `--run-oracle` executes with a "read-only cwd". | The harness cannot enforce an FS-readonly cwd without a sandbox; the real, enforceable mitigation is a command **verb allow-list** (`startd8 …` only) + no-shell + no-network + a self-exec guard. | FR-5 mitigation strengthened from "read-only cwd" to a verb allow-list; a non-allowlisted verb → `skip`, never executed. |

**Resolved open questions:**
- **How is the stage profile built? → via `view_definition.py` (D-1).** Not a literal `RenderProfile`; a registered `ViewDefinition` delta over `base`, like every other domain.
- **What does an oracle `pass` actually guarantee? → the extracted command exited 0 (D-3).** It does not prove the prose assertion; that stays human-checked. This is a deliberately narrow, honest guarantee.
- **Does adding a domain break a test? → no (D-1).** The registry governance assertion is substring-based (`test_sources_and_cli.py:60`); re-run `test_view_definition.py` after, but no count is pinned.

*Backend re-check:* FRs are operator CLI seams (`startd8 navigator build/verify`, console exit codes) → `python-cli-surface` remains correct; no store/cascade retag needed.

### 0.1 Lessons-Learned Hardening (v0.2)

> Checked the SDK/design-doc lessons against the draft. Most were already satisfied by the grounding
> pass; the load-bearing ones, recorded for the trail:

- **[det-req single-line FRs]** — every FR bullet is one physical line carrying `Name:`/`Verify:`/`Serves:` (dogfood-verified via `parse_fr_lines_prefer_kit`: 8/8 named, 8/8 verify).
- **[semantic-names-not-integer-type]** — each FR has a semantic `Name:`; the file keeps its legacy `REQ-08-` brand but the paired plan is DIDL-named (`PLAN-nl-programming-pipeline-provenance.md`).
- **[phantom-reference audit]** — every symbol the spec names was grepped against live code: `node_field_names`, `DEFINITION_REGISTRY`/`validate_definitions`, `to_render_profile`, `chrome_provenance`, `parse_fr_lines_prefer_kit`, `render_tree.py` attribute rows — all exist; `sources_pipeline.py`/`verify_oracle.py`/`pipeline_provenance`/`PIPELINE_DEFINITION` are the to-be-created seams (marked as such).

### 0.2 Design-Principle Hardening (v0.2)

> Checked the draft against the design-principle index. The planning discoveries *were* the principle
> applications:

- **[Kagami — edit source, not mirror]** — `Stage` is `category`+`attributes` over `Node` (no fork); the profile is a `ViewDefinition` delta, not a hand-built copy (D-1); the artifact chain rides a stage-Node attribute, not a bespoke shell (D-5).
- **[Mottainai — don't regenerate]** — `pipeline_provenance` is a sibling in `provenance.py`, not a parallel module (D-4).
- **[Genchi Genbutsu — bind to the real artifact]** — stage status binds to the real `sdk_artifact` resolving on disk, and the profile to the real definition registry (D-1/D-2), not to inferred proxies.
- **[Accidental-complexity anti-principle]** — D-6 replaced a vague "read-only cwd" with one enforceable rule (a verb allow-list), preferring a single rule over an FS-sandbox mechanism the harness can't provide.

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
| security | The `Verify:`-oracle evaluating an authored clause = arbitrary command execution on a review machine | **Default inert**: parse+classify only; execution is opt-in (`--run-oracle`), off by default, argv (no shell interpolation), no network, plus a **verb allow-list** (`startd8 …` only) and a self-exec guard (D-6); prose/manual clauses are never executed | high |
| quality | `Stage` bloating `Node` (a new field / dataclass = a fork) | Kagami: **no** `Node` change — `category="pipeline-stage"` + `attributes` bag only; guard with the existing `node_field_names()` field-compat golden | high |
| quality | Re-inventing provenance instead of extending `chrome_provenance` (Mottainai) | The pipeline-provenance FR **extends** `provenance.py` (a sibling `{element,stage,origin,value,present}` row in the same module — D-4), does not add a parallel module | medium |
| quality | Oracle mis-classifying a prose `Verify:` as a command and "failing" it | Conservative classifier: only a backtick span with an allow-listed verb (`startd8 …`) and resolved placeholders yields a runnable `command_argv`; everything else is `assertion`/`manual` (never fail, surfaced as needs-human), and a `pass` only asserts the extracted command's exit 0 (D-3) | medium |
| quality | Oracle "pass" over-claiming — a green verdict read as "the assertion holds" when only the command's exit code was checked | `pass` is defined narrowly as *the extracted command exited 0*; the prose `assertion_text` rides alongside every verdict as the explicit human-checkable residue (D-3) | medium |

## Functional requirements

- **FR-1 — `Stage` node projection (extend Node, don't fork).** Add `src/startd8/navigator/sources_pipeline.py` projecting the six prose→product stages (intent · functional · contract · impl · test · doc) as `Node`s with `category="pipeline-stage"` and typed `attributes` (ordinal · human_form · sdk_artifact · compiler_analogue · essence), adding **no** field to `Node`; each stage's `status` derives from its `sdk_artifact` resolving on disk (a `code` Lives → `derive_status` = BUILT, like node-schema grounds fields in `models.py`; absent → SPEC), and a `PIPELINE_DEFINITION` (`extends: base`, declaring a built/spec status vocabulary) is added to `view_definition.py` + `DEFINITION_REGISTRY`, projected to `PIPELINE_PROFILE` via `to_render_profile` (D-1/D-2). Name: SDK navigator projects each prose-to-product pipeline stage as a Node using category plus attributes without changing the Node model. Touches: src/startd8/navigator/sources_pipeline.py, src/startd8/navigator/view_definition.py. Lives: doc ~/Documents/craft/THE_NATURAL_LANGUAGE_PROGRAMMING_SYSTEM.md. Approve?: is Stage a projection over Node (category + attributes + a registered pipeline ViewDefinition) with zero Node field changes?. Verify: `node_field_names()` is unchanged AND `nodes_from_pipeline()` returns six nodes each with `category=="pipeline-stage"` and a string `ordinal` attribute (the `attributes` bag is `Dict[str,str]`) whose value parses as an int in 0..5, the six ordinals forming the set {0,1,2,3,4,5}, AND `validate_definitions(DEFINITION_REGISTRY)` stays clean with the new `pipeline` domain. Serves: O-1
- **FR-2 — Stage DEPENDS-ON edges.** Each stage Node carries `child_keys` linking it to the stage(s) it consumes (functional←intent, contract←functional, impl←contract, test←contract, doc←contract) so the pipeline renders as an ordered DAG, reusing the existing DEPENDS-ON `child_keys` field. Name: Navigator wires stage dependency edges via existing child_keys so the pipeline renders as an ordered DAG. Touches: src/startd8/navigator/sources_pipeline.py. Lives: code src/startd8/navigator/sources_pipeline.py. Approve?: do stage edges use child_keys only (no new edge field)?. Verify: `stage:contract` lists `stage:functional` in `child_keys`, `stage:impl`/`stage:test`/`stage:doc` each list `stage:contract`, every referenced key is an emitted stage key, and a topological sort of the stage graph succeeds (no cycle) yielding an order consistent with the FR-1 ordinals. Serves: O-1
- **FR-3 — `--source pipeline` CLI seam.** Extend `cli_navigator.build` with `--source pipeline` (routing to `nodes_from_pipeline()` + the `PIPELINE_PROFILE` projected from the FR-1 `PIPELINE_DEFINITION`), renderable by the existing `--format json|html|a11y` and `--renderer tree|graph`, additive with no break to existing sources. Name: Navigator CLI exposes a pipeline source that renders the six stages through the existing renderers. Touches: src/startd8/navigator/cli_navigator.py, src/startd8/navigator/sources_pipeline.py. Lives: code src/startd8/navigator/cli_navigator.py. Approve?: is `--source pipeline` additive (existing sources/formats unchanged)?. Verify: `startd8 navigator build --source pipeline --format json` exits 0 with six nodes; `--source requirements|capability-index|node-schema|nodes-json` behave unchanged. Serves: O-1
- **FR-4 — Verify-as-oracle: parse + classify (extract the runnable span).** Add a `verify_oracle` module that reads a det-req doc's parsed FRs (via `det_req.parse_fr_lines_prefer_kit`) and classifies each authored Verify-clause by **extracting** its runnable span rather than bucketing the whole clause: `command` (the clause contains a backtick-quoted span whose first token is an allow-listed verb — `startd8 …` (opt. `$ …`) — and no unresolved placeholder like `<doc>`/`…`), `assertion` (prose acceptance, no runnable span), or `manual` (explicitly human, or a command whose placeholders don't resolve) — producing a typed per-FR descriptor (`kind`, `command_argv`, `assertion_text`, `reason`), no execution (D-3). Name: SDK navigator parses each requirement Verify-clause into a typed acceptance-oracle descriptor extracting the runnable command span and classifying command assertion or manual. Touches: src/startd8/navigator/verify_oracle.py. Lives: code src/startd8/navigator/verify_oracle.py. Approve?: does the classifier extract a runnable span only for an allow-listed-verb backtick command with resolved placeholders (everything else assertion/manual), reading FRs via the existing det_req.parse_fr_lines_prefer_kit without modifying det_req.py?. Verify: for a fixture doc each FR yields a descriptor with `kind in {command,assertion,manual}`; a mixed clause (backtick `startd8 …` command + prose assertion) yields `kind=command` with `command_argv` set and the prose retained in `assertion_text`; a prose-only or unresolved-placeholder clause is `assertion`/`manual`, never `command`. Serves: O-2
- **FR-5 — `Verify:`-as-oracle: opt-in evaluate + pass/fail.** Add `startd8 navigator verify --requirements <doc>` that reports a per-FR verdict (`pass|fail|skip`): by default it evaluates nothing (inert — every `command`/`manual` clause reports `skip`, no subprocess), and only with `--run-oracle` does it execute the extracted `command_argv` (no shell interpolation, no network) where **`pass` = the extracted command exited 0** and `fail` = non-zero — the prose `assertion_text` is emitted alongside as the human-checkable residue, **not** machine-asserted; execution is guarded by a verb **allow-list** (only `startd8 …`; any other verb → `skip`, reason "non-allowlisted") and a self-exec guard (refuse a `startd8 navigator verify … --run-oracle` command to prevent recursion) (D-3/D-6). Name: Navigator verify command reports a per-requirement pass-fail-skip verdict defaulting inert and executing allow-listed command oracles only under an explicit opt-in flag. Touches: src/startd8/navigator/cli_navigator.py, src/startd8/navigator/verify_oracle.py. Lives: code src/startd8/navigator/verify_oracle.py. Approve?: is oracle execution off by default and safe (argv/no-shell/no-network/verb-allowlist/self-exec-guard) under `--run-oracle`, with `pass` meaning only "the extracted command exited 0"?. Verify: `startd8 navigator verify --requirements <doc>` exits 0 emitting only `skip` verdicts with no subprocess spawned; `--run-oracle` runs allow-listed command-kind clauses via argv (never `shell=True`) and reports pass=rc0/fail=rc≠0, a non-allowlisted verb stays `skip`; exit code is 0 when no verdict is `fail` (all-`skip` inert runs included) and non-zero iff at least one `fail` is present, so CI can gate on the process rc. Serves: O-2
- **FR-6 — Pipeline provenance trace (extend provenance.py).** Add `pipeline_provenance(nodes, stages)` alongside `chrome_provenance` in `src/startd8/navigator/provenance.py` returning, for a given FR (or a `Touches`/`Lives` file), the ordered artifact→stage→requirement chain as a **sibling row schema** `{element, stage, origin, value, present}` (the same module and element→origin→present idea as `chrome_provenance`, adding a `stage` column and keeping `value` for parity — a sibling function, not a shape-identical reuse, since `chrome_provenance`'s signature is `(nodes, plan, profile)`) — extending, not replacing, `chrome_provenance` (D-4). Name: SDK navigator extends provenance to trace a delivered artifact back through the pipeline stages to its originating requirement. Touches: src/startd8/navigator/provenance.py, src/startd8/navigator/sources_pipeline.py. Lives: code src/startd8/navigator/provenance.py. Approve?: does pipeline provenance extend provenance.py (a sibling row schema in the same module) rather than add a parallel module?. Verify: `pipeline_provenance` lives in `provenance.py` next to `chrome_provenance`, emits rows with keys `{element,stage,origin,value,present}`, and for an FR with a code `Lives:` ref returns an ordered chain whose stages are a subsequence of the FR-1 stage ordinals ending at the requirement. Serves: O-3
- **FR-7 — `verify`/provenance render surface.** Surface the oracle verdicts and the pipeline-provenance chain through the existing renderers: the `verify` command supports `--format json|html`, and the pipeline-provenance rows are folded onto each stage Node's `attributes["artifact_chain"]` (which `render_tree.py` already surfaces as meta rows — so the chain is a **tree** affordance; the graph renderer shows the stage DAG) — no new HTML shell (D-5). Name: Navigator renders oracle verdicts and the pipeline-provenance chain through the existing renderers without a new HTML shell. Touches: src/startd8/navigator/cli_navigator.py, src/startd8/navigator/sources_pipeline.py. Lives: code src/startd8/navigator/cli_navigator.py. Approve?: do verdicts + provenance reuse the existing renderers (chain as a stage-Node attribute, no bespoke shell)?. Verify: `startd8 navigator verify --requirements <doc> --format json` emits a per-FR verdict array; `--source pipeline --renderer tree` renders stage nodes whose `artifact_chain` attribute appears as meta rows, and `--renderer graph` renders the stage DAG. Serves: O-2, O-3
- **FR-8 — Byte-identity + field-compat guard.** The pipeline source, oracle, and provenance extension are standalone/additive: `Node` is unchanged, the app-scaffold wireframe path is byte-identical, the field-compat golden passes unedited, and adding the `pipeline` domain leaves the definition registry governance clean (D-1). Name: The pipeline source and oracle and provenance extension leave Node and the app-scaffold path byte-identical. Touches: tests/unit/navigator/test_pipeline_source.py, tests/unit/wireframe/test_render_profile.py. Lives: test tests/unit/wireframe/test_render_profile.py. Approve?: is Node/app-scaffold untouched and the registry still clean with the new domain?. Verify: `node_field_names()` golden + `test_no_profile_is_byte_identical` pass unedited, `validate_definitions(DEFINITION_REGISTRY)` returns no issues with the `pipeline` domain present, and no new module imports `wireframe_view` for the pipeline/oracle path. Serves: O-4

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
`src/startd8/navigator/cli_navigator.py`, `src/startd8/navigator/view_definition.py`
(add the `pipeline` ViewDefinition + registry entry — D-1).
Read-only imports (not edited): `src/startd8/navigator/det_req.py`
(`parse_fr_lines_prefer_kit` — consumed by the oracle, unchanged); `src/startd8/navigator/models.py`
(`Node` consumed, no field added — NR-3).

## Appendix A — Accepted (with where merged)
## Appendix B — Rejected (with rationale)
## Appendix C — Incoming review rounds

*v0.1 — extracts the three repo-able artifacts of the Natural-Language Programming System thesis
(`Stage` node type · `Verify:`-as-oracle · end-to-end pipeline provenance) as additive navigator
changes. Philosophy in the Overview; FRs grounded to verifiable navigator behavior. Ready for CRP.*
*v0.1.1 — pre-CRP grounding fixes: FR-1 `ordinal` typed as string-parseable-int (bag is `Dict[str,str]`);
FR-2 Verify asserts a real topological sort (not just subset); FR-4 `Touches` narrowed to `verify_oracle.py`
(det_req.py is a read-only import); FR-5 defines aggregate exit-code semantics for CI gating.*
*v0.2 — Post-planning self-reflective update (see §0 + `PLAN-nl-programming-pipeline-provenance.md`).
6 discoveries folded in: D-1 profile built via `view_definition.py` ViewDefinition/registry (FR-1/FR-3
Touch it); D-2 stage status derives from `sdk_artifact` + a pipeline status vocabulary; D-3 Verify
clauses mix command+assertion — FR-4 extracts the runnable span, FR-5 `pass`=command rc0 with the
assertion as human residue; D-4 provenance is a sibling row schema, not shape-identical; D-5 the chain
renders as a stage-Node attribute (tree); D-6 `--run-oracle` uses a verb allow-list + self-exec guard.
0 FRs removed, 0 added; 6 refined. Ready for CRP.*
