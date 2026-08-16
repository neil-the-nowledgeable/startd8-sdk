# Implementation Plan — Natural-Language Programming Pipeline & End-to-End Provenance

**Project:** startd8-sdk   **Pairs with:** `REQ-08-nl-programming-pipeline-provenance.md`
**Version:** 1.0   **Date:** 2026-08-15
**Semantic name:** *Plan for seating each prose→product pipeline stage as a Node, promoting the `Verify:` clause to an acceptance oracle, and tracing a delivered artifact back through the stages to its requirement.*
**Canonical ref:** `cc:intent:requirements-visualization:plan:req-08`

> This plan was produced by the `/reflective-requirements` loop as the Phase-2 pass over REQ-08 v0.1.
> Every FR was mapped to concrete `navigator/` files at real line ranges; the discoveries it surfaced
> are folded back into REQ-08 §0 (v0.2). Read §0 of the REQ for the corrections; this file is the how.

---

## Seam map (what actually exists, from reading the code)

| Seam | File:line | What it means for this REQ |
|------|-----------|----------------------------|
| Source pattern | `sources_node_schema.py:69` `nodes_from_node_schema()` | The exact template for `nodes_from_pipeline()`: build `Node`s with `category` + curated `attributes`; every node carries a `code` Lives so `status` derives via `derive_status`. |
| Profile is **not** a literal | `view_definition.py:377-415` | All 3 real domains are a `ViewDefinition(extends="base", vocabulary=…, chrome=…)` registered in `DEFINITION_REGISTRY`, then `PROFILE = to_render_profile(resolve(DEF, REGISTRY))`. A `PIPELINE_PROFILE` must follow suit — **this file is a Touches the v0.1 spec omitted.** |
| CLI routing | `cli_navigator.py:99-140` | `--source pipeline` is a clean additive `elif` returning `(nodes, PIPELINE_PROFILE, project_root=".")`; the renderer resolution (`:140`) and json/html/a11y arms need no change. |
| Renderers ignore profile (except wireframe) | `cli_navigator.py:162-184` | tree/graph/a11y take `list(nodes)` only — so `--source pipeline --renderer graph|tree` and `--format a11y` work the moment nodes exist. FR-7 is cheap. |
| Attributes render in tree | `render_tree.py:50,151` | Arbitrary `attributes` become meta rows — so the FR-7 "artifact-chain annotation" is just a stage-Node attribute; **no renderer edit**. Graph (`render_graph.py:401`) reads attributes only for href, so the chain surfaces in *tree*, not graph. |
| Verify clause is prose | `det_req.py:19-21` `_VERIFY_LABEL` → `fr["verify"]` (a string) | The oracle classifies this string. **Crucially, real clauses mix a backtick command with a prose assertion** (see D-3) — the classifier can't treat the whole clause as one atomic kind. |
| chrome_provenance row shape | `provenance.py:27-48` | rows are `{element, origin, value, present}`, signature `(nodes, plan, profile)`. `pipeline_provenance` is a **sibling** with a related-but-different row + signature — "extends provenance.py" (same module/idea) but not shape-identical (see D-4). |
| Registry governance test | `tests/unit/navigator/test_sources_and_cli.py:60` | asserts substring `"definitions valid"` (count-agnostic) → adding the `pipeline` domain keeps it green, but re-run `test_view_definition.py` after. **Caveat (R1-S3):** `validate_definitions` (`view_definition.py:421-442`) checks only `extends` chains + `chrome.bindings` — NOT status-map well-formedness; FR-8 must add its own status-vocab assertion. |

---

## Per-FR implementation

### FR-1 + FR-2 — `sources_pipeline.py` (Stage projection + DEPENDS-ON edges)
- **New:** `src/startd8/navigator/sources_pipeline.py`, modeled line-for-line on `sources_node_schema.py`.
- A module-level `_STAGES` table: 6 rows `(key, ordinal, human_form, sdk_artifact, compiler_analogue, essence, does, child_keys)`.
  Concrete `sdk_artifact` per stage, resolved via `(repo_root / sdk_artifact).exists()` where
  `repo_root = Path(__file__).resolve().parents[3]` (as `sources_node_schema._repo_root`) **(R1-S2):**

  | key | ord | sdk_artifact (primary) | compiler_analogue | essence |
  |-----|-----|------------------------|-------------------|---------|
  | `stage:intent` | 0 | `src/startd8/seeds/` | source text (the prose brief) | essential |
  | `stage:functional` | 1 | `src/startd8/navigator/det_req.py` | lexer/parser → FR tokens | essential |
  | `stage:contract` | 2 | `src/startd8/forward_manifest.py` | IR (the contract/Node) | essential |
  | `stage:impl` | 3 | `src/startd8/backend_codegen/` | code-gen back-end / interpreter | accidental |
  | `stage:test` | 4 | `src/startd8/backend_codegen/test_emitter.py` | oracle (tests from `Verify:`) | accidental |
  | `stage:doc` | 5 | `docs/` | man-page | accidental |

  Edges: `stage:intent`(0) → `stage:functional`(1) → `stage:contract`(2) → {`stage:impl`(3), `stage:test`(4), `stage:doc`(5)}.
  Resolution: `.exists()` **exact path** for status; **provenance ownership (FR-6) uses longest-prefix match**
  of the queried path against the `sdk_artifact` set (R1-S8).
- `nodes_from_pipeline()` builds one `Node` per row: `category="pipeline-stage"`, `child_keys=<edges>`,
  `attributes={kind:"stage", ordinal:str(n), human_form, sdk_artifact, compiler_analogue, essence, …}`.
- **Status (D-2), corrected API (R1-S1):** `sdk_artifact` resolving on disk → a `code` Lives →
  `derive_status(has_code_evidence=True, maturity="stable")` — the **real** signature is
  `derive_status(*, has_code_evidence: bool, maturity: str)` (`models.py:98`; `sources_requirements.py:184`
  passes `maturity="stable"`) → BUILT; artifact absent → SPEC. The constant `maturity="stable"` closes the
  vocabulary to {built, spec} (never THIN).
- `PIPELINE_DEFINITION` added to `view_definition.py` + registered in `DEFINITION_REGISTRY`;
  `PIPELINE_PROFILE = to_render_profile(resolve(PIPELINE_DEFINITION, DEFINITION_REGISTRY))`. Its
  `vocabulary.statuses` is **keyed by the `NodeStatus` ids** `derive_status` emits (`built`, `spec`) — not
  prose labels — matching every domain (`view_definition.py:245-254`) so the legend resolves each stage's
  real status (R1-S4).
- **Verify (topo-sort, per REQ FR-2 v0.1.1):** `graphlib.TopologicalSorter` over the stage graph — succeeds,
  order agrees with ordinals.
- **Deps:** none. First to build.

### FR-3 — `--source pipeline` CLI seam
- Edit `cli_navigator.py`: add `elif source == "pipeline": nodes = nodes_from_pipeline(); profile = PIPELINE_PROFILE; project_root = "."` at `:116`-style; extend the `--source` help + the unknown-source error string (`:64`, `:131`).
- **Verify:** `startd8 navigator build --source pipeline --format json` exits 0, 6 nodes; existing sources unchanged (assert the 4 prior `--source` values still behave).
- **Deps:** FR-1.

### FR-4 — `verify_oracle.py`: parse + classify  *(revised by D-3)*
- **New:** `src/startd8/navigator/verify_oracle.py`. Reads FRs via `det_req.parse_fr_lines_prefer_kit` (import only — `det_req.py` unedited, per REQ v0.1.1).
- Classifier operates on the clause and **extracts** the runnable span rather than bucketing the whole
  clause atomically:
  - `command` — clause contains **exactly one** backtick-quoted span whose first token is an allow-listed
    verb (`startd8 …`; optionally `$ …`) **and** no unresolved placeholder.
  - **Multi-span rule (R1-S5):** a clause with **two or more** runnable backtick spans, or a `;`/`&&`/`|`-joined
    command inside one span, classifies as `manual` (reason "multi-command") — deterministic, never guesses which wins.
  - **Placeholder grammar — closed set (R1-F5):** a span is disqualified (→ `manual`, reason "unresolved placeholder")
    if it contains any of: `<…>` (angle), `…`/`...` (ellipsis), `${…}`/`$WORD` (shell var), `{…}` (brace), `[…]` (bracket).
  - `assertion` — prose acceptance with no runnable span.
  - `manual` — explicitly human (`Approve?:`-style / "by inspection"), multi-command, or unresolved-placeholder.
- Descriptor: `{fr_id, kind, command_argv|None, assertion_text, reason}`.
- **Deps:** none (parallel with FR-1).

### FR-5 — `startd8 navigator verify` + opt-in evaluate  *(revised by D-3, D-6)*
- New `@navigator_app.command("verify")` in `cli_navigator.py`; `--requirements <doc>`, `--run-oracle` (default OFF), `--format json|html`.
- Default inert: every descriptor → `skip`, **no subprocess**.
- `--run-oracle`: for `command`-kind only, run `command_argv` via `subprocess.run(argv, shell=False, timeout=…)`.
  **pass = exit 0 of the extracted command; fail = non-zero.** The prose `assertion_text` is *not* asserted
  by the run — it rides alongside as the human-checkable residue.
- **Read-only subcommand allow-list (R1-S6/R1-F7):** the allow-list gates the *verb AND the subcommand* — only
  read-only `startd8 navigator …` invocations that **write nothing** run; any command with a write flag
  (`--out`, `--fix`), a non-`navigator` verb (`generate`, `deploy`, …), or a non-`startd8` verb → `skip`
  (reason "side-effecting/non-allowlisted"). This — not "no network" — is what preserves the O-4/NR-1
  "models, does not mutate" invariant.
- **No-network honesty (R1-F6):** network-denial for the child is *not* argv-enforceable (a `startd8`
  subcommand could open a socket); the real, stated guarantee is the read-only allow-list + no-shell, and the
  chosen read-only navigator subcommands don't hit the network.
- **Self-exec guard (R1-S7):** matched on **resolved argv tokens** (`argv[:3] == ["startd8","navigator","verify"]`),
  not a substring of the raw clause — so quoting/whitespace variants can't evade and a clause merely *mentioning*
  the phrase doesn't false-trip.
- **Timeout (R1-S9):** `timeout=60` default (exposed as `--oracle-timeout`); a timeout is a **distinct** verdict
  (`fail`, reason "timeout"), not conflated with rc≠0.
- **Missing-path (R1-S5):** a command whose referenced fixture path is absent → a distinct `error` verdict
  (reason "missing input"), *not* a silent assertion `fail`.
- Aggregate exit code (REQ FR-5 v0.1.1): 0 when no `fail` (and no `error`), non-zero iff any `fail`/`error`.
- **Deps:** FR-4.

### FR-6 — `pipeline_provenance()` in `provenance.py`  *(revised by D-4)*
- Add `pipeline_provenance(nodes, stages)` **beside** `chrome_provenance` (same module — Mottainai).
- Row schema: `{element, stage, origin, value, present}` — keeps `value` for parity with the sibling,
  adds `stage`. (v0.1 said "same element→origin→value shape"; it's a sibling schema, now stated so.)
- For a given FR (or a `Touches`/`Lives` file): walk artifact → the stage that owns it → … → the requirement,
  emitting an ordered chain whose stage ordinals are a subsequence of FR-1's.
- **Ownership tie-break + not-found (R1-S8):** an artifact is owned by the stage with the **longest-prefix**
  `sdk_artifact` match (deterministic when one path is a prefix of another); an artifact matching **no** stage
  yields a single row with `present=False` (reason "unowned"), never an empty chain.
- **SPEC stages still surface (R1-S10):** a chain passing through an un-built (SPEC) stage still emits that
  stage's row (with its not-built status) so the trace *shows the gap* rather than silently skipping it (Mieruka).
- **Deps:** FR-1 (needs the stage table).

### FR-7 — render surface
- `verify` supports `--format json|html` (json = per-FR verdict array; html via an existing renderer, no new shell).
- Pipeline provenance rendered by folding each stage's downstream chain onto that stage Node's
  `attributes["artifact_chain"]` (surfaces as tree meta rows — `render_tree.py:151`). Graph shows the
  stage DAG; the chain annotation is a tree affordance. **No new HTML shell** (NR-6).
- **Deps:** FR-5, FR-6.

### FR-8 — byte-identity + field-compat guard  *(widened by D-1)*
- New `tests/unit/navigator/test_pipeline_source.py`; `node_field_names()` golden + `test_no_profile_is_byte_identical` pass unedited.
- **Added by planning:** also assert `validate_definitions(DEFINITION_REGISTRY)` stays clean with the new
  `pipeline` domain, and re-run `test_view_definition.py` / `test_sources_and_cli.py` (the registry now has
  5 domains; the governance assertion is substring-based so it holds, but confirm).
- **`validate_definitions` is NOT a status-vocab guard (R1-S3):** it only checks `extends` chains +
  `chrome.bindings` (`view_definition.py:421-442`) — it does **not** validate status-map well-formedness.
  So FR-8 adds its **own** assertion: iterate `PIPELINE_PROFILE.statuses` and require each has a non-empty
  `label`/`meaning`/`color` and an int `severity`. Do not lean on `validate_definitions` for this.
- **Deps:** all.

---

## Build order

```
FR-1 ─┬─ FR-2 (edges, same module)
      ├─ FR-3 (CLI source)
      └─ FR-6 (provenance) ─┐
FR-4 ── FR-5 ───────────────┼─ FR-7 (render) ── FR-8 (guards, last)
                            ┘
```
FR-1 and FR-4 are independent roots and can go in parallel.

## Discoveries fed back to REQ-08 (see REQ §0, v0.2)

| # | v0.1 assumed | Planning found | Impact |
|---|--------------|----------------|--------|
| D-1 | FR-1/FR-3 build a `PIPELINE_PROFILE` | Profiles are `ViewDefinition(extends=base)` entries in `DEFINITION_REGISTRY` projected via `to_render_profile` | Add `view_definition.py` to FR-1/FR-3 Touches; add a pipeline domain def + registry entry |
| D-2 | Stages just have `attributes` | Stages need a **status vocabulary** + an evidence model; `sdk_artifact`-resolves-on-disk → BUILT (like node-schema) | FR-1: stage status derives from `sdk_artifact`; pipeline def declares built/spec statuses |
| D-3 | `Verify:` clause is atomically `command`/`assertion`/`manual` | Real clauses **mix** a backtick command + a prose assertion; argv-exec can only check the command's **exit code**, not the assertion | FR-4 extracts the runnable span (+ placeholder/verb guards); FR-5 `pass` = extracted command rc0, assertion is human residue |
| D-4 | `pipeline_provenance` reuses the **same** `element→origin→value` row shape | chrome rows are `{element,origin,value,present}` w/ sig `(nodes,plan,profile)`; pipeline is a **sibling** `{element,stage,origin,value,present}` w/ `(nodes,stages)` | FR-6 states it's a sibling schema in the same module, not shape-identical |
| D-5 | Provenance "renderable as Nodes" | The trace is **rows**, not Nodes; must fold onto stage-Node `attributes` to render (tree only) | FR-7: annotate stage Nodes via `attributes["artifact_chain"]`; chain is a tree affordance |
| D-6 | `--run-oracle` uses "read-only cwd" | The harness can't enforce an FS-readonly cwd; real mitigation is a **verb allow-list** (`startd8 …` only) + no-shell + no-net + self-exec guard | FR-5 mitigation strengthened to a command allow-list |

*v1.0 — plan mapped every FR to real `navigator/` seams; 6 discoveries (D-1..D-6) folded into REQ-08 v0.2. FR-1 and FR-4 are independent build roots.*
*v1.1 — CRP R1 triage applied (all 10 S-suggestions ACCEPTED; dispositions in Appendix A): S1 fixed the
`derive_status` signature (+`maturity="stable"`); S2 added the concrete `_STAGES` `sdk_artifact` table +
resolution rule; S3 corrected the `validate_definitions` over-claim (FR-8 adds its own status-vocab assertion);
S4 keyed the status vocab by `NodeStatus` ids; S5 defined multi-command/missing-path handling; S6 restricted
`--run-oracle` to read-only navigator subcommands; S7 argv-token self-exec guard; S8 longest-prefix ownership +
not-found row; S9 `--oracle-timeout` (60s) distinct verdict; S10 SPEC-stage rows surface. Paired REQ items
F1..F7 applied in REQ-08 v0.3.*

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
| (none yet) |  |  |  |  |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-08-16 04:05:00 UTC
- **Scope**: Plan-side review (S-prefix), weighted per sponsor focus toward the per-FR seam mapping / build order, the D-3 Verify-oracle design, and the FR-5 security surface. Grounded against `src/startd8/navigator/{models.py,view_definition.py,det_req.py,cli_navigator.py,provenance.py}` (targeted reads, no edits). Respects settled D-1..D-6.

**Executive summary (top plan risks/gaps):**
- The FR-1 seam text ("`derive_status(has_code_evidence=True)`") does not match the real signature `derive_status(*, has_code_evidence, maturity)` (models.py:98) — the plan's status-derivation line will not compile as written and omits how `maturity` (BUILT vs THIN) is chosen.
- The plan never names the concrete `sdk_artifact` path per stage nor the resolution rule (dir vs file, exact vs prefix), yet FR-1 status derivation and FR-6 provenance both hinge on it. This is the load-bearing, un-specified table.
- FR-8's acceptance (and §-seam-map row for `test_sources_and_cli.py:60`) treats `validate_definitions` as governing the new domain's status vocabulary; it does not (only extends-chains + bindings) — the guard is weaker than the plan implies.
- The D-3 extract-the-runnable-span logic has no plan-level handling for multi-command / `;`-joined clauses or for a command referencing a fixture path that doesn't exist (rc≠0 → spurious `fail`). Build order puts FR-4/FR-5 on the critical path with these unresolved.
- FR-5's verb allow-list gates the *verb* `startd8` but not the *subcommand*; the plan has no step to distinguish read-only (`navigator build --format json`) from mutating (`generate backend`, `--out`) subcommands — a repo-mutation escape from the "modeling only" invariant.
- FR-6's `pipeline_provenance(nodes, stages)` walk ("artifact → the stage whose `sdk_artifact`/kind owns it") has no tie-break when two stages could own an artifact, and no plan step for the not-found case.
- The self-exec guard is specified by string-matching the command; the plan should say it matches on resolved argv tokens (verb+subcommand), not a substring, to avoid trivial evasion/false-trip.

**Numbered suggestions (S-prefix):**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Data | high | Fix the FR-1 status-derivation line to the real API and add `maturity`. The plan writes `derive_status(has_code_evidence=True)`; the actual signature is `derive_status(*, has_code_evidence: bool, maturity: str)` (models.py:98) and maturity picks BUILT vs THIN. Specify the per-stage (or constant) maturity the projection passes. | As written the call is wrong and would fail at build time; the built/spec vocabulary story (D-2) silently breaks if a stage resolves THIN. | "Per-FR implementation → FR-1 → Status (D-2)" bullet | Grep the code for `derive_status(` signature; unit-assert stage statuses ∈ {built, spec}. |
| R1-S2 | Data | high | Add the concrete `_STAGES` `sdk_artifact` column with real paths and the resolution rule. The plan names the 8-tuple `(key, ordinal, human_form, sdk_artifact, compiler_analogue, essence, does, child_keys)` but gives only one example (`backend_codegen/`); FR-1 status + FR-6 provenance both depend on exact paths and whether resolution is dir-exists / file-exists / prefix-match, relative to which root (`project_root="."`). | This is the single most load-bearing un-specified artifact; two implementers will pick different paths and roots, and FR-6's "stage that owns the artifact" is undefined without it. | New sub-bullet under FR-1 (`_STAGES` table) | Fixture repo → assert each stage's `sdk_artifact` resolves as documented and yields the expected status. |
| R1-S3 | Validation | high | Correct the FR-8 / seam-map claim that `validate_definitions` proves the pipeline vocabulary clean. Per view_definition.py:421-442 it validates only `extends` chains + `chrome.bindings`; it does not check status-map well-formedness (label/meaning/color/severity). Either add an explicit status-vocab assertion to the FR-8 step or drop the implication. | The plan (FR-8 "also assert `validate_definitions` stays clean") and the seam-map governance row over-state the guard, risking a false green when the pipeline status map is malformed. | "Per-FR implementation → FR-8" + seam-map row `test_sources_and_cli.py:60` | Add an assertion iterating the resolved profile's statuses for non-empty required fields. |
| R1-S4 | Interfaces | high | Require the pipeline status vocabulary to be keyed by the `NodeStatus` ids emitted by `derive_status` (`built`/`spec`/`thin`), matching how every domain keys `vocabulary.statuses` (view_definition.py:245-254). Add this to the FR-1 build step. | If the `PIPELINE_DEFINITION` keys statuses by prose labels, the legend/status band won't resolve the stage's real status — an orphan chrome the D-1 audit is supposed to prevent. | FR-1 `PIPELINE_DEFINITION` bullet | Assert resolved `profile.statuses` keys ⊇ the set of statuses `nodes_from_pipeline()` emits. |
| R1-S5 | Risks | high | Add a plan step for multi-span and non-existent-path Verify clauses in FR-4/FR-5. Define: (a) multiple backtick / `;`/`&&`-joined commands → documented rule (first allow-listed span, or `manual`); (b) an extracted command whose fixture path is absent → rc≠0 → decide `fail` vs a distinct `error`/`skip` so a missing-fixture doesn't masquerade as an assertion failure. | The sponsor flags these exact cases; both are on the FR-4→FR-5 critical path and undefined, so `pass`/`fail` semantics are non-deterministic. | FR-4 classifier bullets + FR-5 evaluate bullet | Fixtures: 2-command clause, `;`-joined clause, missing-path command → assert documented verdicts. |
| R1-S6 | Security | high | Split the FR-5 allow-list into verb **and** subcommand policy. The plan allow-lists the verb `startd8` but a subcommand can mutate the repo (`generate backend`, `navigator build --out …`). Add a step to restrict `--run-oracle` to read-only subcommands (or explicitly document mutation as accepted risk). | The verb allow-list does not preserve the O-4 / NR-1 "models, does not mutate" invariant for the oracle path; an authored clause can smuggle a side-effecting `startd8` subcommand. | FR-5 "verb allow-list" bullet | Fixture clause `startd8 generate …` under `--run-oracle` → assert refused/flagged, repo unchanged. |
| R1-S7 | Security | medium | Specify the self-exec guard as an argv-token match (verb+subcommand = `startd8 navigator verify`), not a substring of the raw clause. The plan says "refuse a command that is itself `startd8 navigator verify … --run-oracle`". | A substring match both under-matches (quoting/whitespace variants evade) and over-matches (a doc *mentioning* the string trips it); argv-token comparison is deterministic. | FR-5 "Self-exec guard" bullet | Unit test: argv `["startd8","navigator","verify",...]` refused; a clause merely quoting the phrase is not. |
| R1-S8 | Interfaces | medium | Define FR-6's artifact→stage ownership tie-break and not-found case. "walk artifact → the stage whose `sdk_artifact`/kind owns it" is ambiguous when an artifact path is a prefix of two stages' artifacts, and undefined when no stage owns it. | Provenance rows are meaningless if ownership is nondeterministic; a not-found artifact needs a defined row (`present=False`) rather than an empty chain. | FR-6 walk bullet | Fixtures: overlapping-path artifact (assert deterministic owner), unowned artifact (assert `present=False` row). |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S9 | Risks | medium | Add a `--timeout` default and behavior-on-timeout to FR-5. The plan shows `subprocess.run(argv, shell=False, timeout=…)` with `…` unfilled; a hung allow-listed command would block the whole `verify` run. Define the default and the timeout verdict (`fail` with reason, distinct from rc≠0). | An unspecified timeout is a real DoS/hang surface on the review machine, and conflating timeout with rc≠0 loses signal. | FR-5 evaluate bullet | Fixture command that sleeps > timeout → assert a bounded, distinctly-labeled verdict. |
| R1-S10 | Ops | low | Note that FR-6's "stage ordinals are a subsequence of FR-1's" must hold even when stages are SPEC (artifact absent). A provenance chain through an un-built stage should still emit the stage row (present flag) so the trace shows the gap rather than skipping it. | The most useful provenance output is one that surfaces the *missing* stage; silently dropping SPEC stages hides exactly the gap an operator wants (Mieruka). | FR-6 walk bullet / FR-7 render | Fixture where an intermediate stage is SPEC → assert its row appears with a not-built marker. |

**Endorsements & Disagreements:** none — this is R1; Appendix C had no prior untriaged rounds. (Cross-doc note: S-suggestions R1-S1/S3/S4 pair with requirements items R1-F1/F3/F2 respectively; S5 pairs with F4; S6 pairs with F7 — the orchestrator may triage them together.)

---

## Requirements Coverage Matrix — R1

Analysis only (not triage). Each REQ-08 FR/objective → the plan section that implements it → Covered / Partial / Gap. "Partial" rows generated the correspondingly-numbered S-suggestion above.

| Requirement (REQ-08) | Plan Section / Task | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-1 — `Stage` node projection + status vocabulary (D-1/D-2) | Per-FR → FR-1+FR-2; seam-map rows 1-2 | Partial | `derive_status` call signature wrong + `maturity` unspecified (R1-S1); concrete per-stage `sdk_artifact` paths + resolution rule absent (R1-S2); status vocab must key by `NodeStatus` ids (R1-S4). |
| FR-2 — Stage DEPENDS-ON edges (topo-sort) | Per-FR → FR-1+FR-2 (edges); build order | Full | Edges + `graphlib.TopologicalSorter` acceptance are concrete and grounded to `child_keys`. |
| FR-3 — `--source pipeline` CLI seam | Per-FR → FR-3; seam-map CLI-routing row | Full | Additive `elif` + help/error string edits at real line ranges; existing-source non-regression asserted. |
| FR-4 — Verify-oracle parse + classify (D-3) | Per-FR → FR-4 | Partial | No rule for multi-command / `;`-joined clauses (R1-S5); placeholder grammar not a closed set (see REQ R1-F5). |
| FR-5 — opt-in evaluate + pass/fail (D-3/D-6) | Per-FR → FR-5 | Partial | Subcommand (not just verb) mutation risk (R1-S6); self-exec guard match method (R1-S7); non-existent-path → spurious `fail` (R1-S5); `--timeout` default/verdict unset (R1-S9). |
| FR-6 — Pipeline provenance sibling schema (D-4) | Per-FR → FR-6 | Partial | Artifact→stage ownership tie-break + not-found row undefined (R1-S8); SPEC-stage rows should still surface (R1-S10). |
| FR-7 — verify/provenance render surface (D-5) | Per-FR → FR-7 | Full | Reuses tree meta-rows + graph DAG at real seams (`render_tree.py:151`); no new shell — well-grounded. |
| FR-8 — byte-identity + field-compat guard (D-1) | Per-FR → FR-8 | Partial | `validate_definitions` does not check status-vocab well-formedness — over-claimed as a guard (R1-S3). |
| O-1 — pipeline as Nodes, rendered | FR-1/FR-2/FR-3/FR-7 | Full | Covered by the above. |
| O-2 — `Verify:` as acceptance oracle | FR-4/FR-5/FR-7 | Partial | Inherits FR-4/FR-5 gaps (multi-span, security, timeout). |
| O-3 — artifact→stage→requirement trace | FR-6/FR-7 | Partial | Inherits FR-6 ownership/not-found gaps. |
| O-4 — standalone/additive, byte-identical | FR-8 | Partial | Byte-identity golden is solid; the "no mutation" invariant is not actually enforced for the `--run-oracle` path (R1-S6). |
