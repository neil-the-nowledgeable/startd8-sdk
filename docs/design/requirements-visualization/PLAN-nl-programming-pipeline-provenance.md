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
| Registry governance test | `tests/unit/navigator/test_sources_and_cli.py:60` | asserts substring `"definitions valid"` (count-agnostic) → adding the `pipeline` domain keeps it green, but re-run `test_view_definition.py` after. |

---

## Per-FR implementation

### FR-1 + FR-2 — `sources_pipeline.py` (Stage projection + DEPENDS-ON edges)
- **New:** `src/startd8/navigator/sources_pipeline.py`, modeled line-for-line on `sources_node_schema.py`.
- A module-level `_STAGES` table: 6 rows `(key, ordinal, human_form, sdk_artifact, compiler_analogue, essence, does, child_keys)`.
  - `stage:intent`(0) → `stage:functional`(1) → `stage:contract`(2) → {`stage:impl`(3), `stage:test`(4), `stage:doc`(5)}.
- `nodes_from_pipeline()` builds one `Node` per row: `category="pipeline-stage"`, `child_keys=<edges>`,
  `attributes={kind:"stage", ordinal:str(n), human_form, sdk_artifact, compiler_analogue, essence, …}`.
- **Status (D-2):** each stage's `sdk_artifact` (e.g. `src/startd8/backend_codegen/`) resolves on disk → a
  `code` Lives → `derive_status(has_code_evidence=True)` = BUILT, exactly like node-schema grounds fields
  in `models.py`. Stages whose artifact is absent fall to SPEC. This needs a status **vocabulary** in the
  pipeline `ViewDefinition` (built/spec), which the v0.1 spec didn't name.
- `PIPELINE_DEFINITION` added to `view_definition.py` + registered in `DEFINITION_REGISTRY`;
  `PIPELINE_PROFILE = to_render_profile(resolve(PIPELINE_DEFINITION, DEFINITION_REGISTRY))`.
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
  - `command` — clause contains a backtick-quoted span whose first token is an allow-listed verb
    (`startd8 …`; optionally `$ …`) **and** contains no unresolved placeholder (`<doc>`, `…`, `<…>`).
  - `assertion` — prose acceptance with no runnable span.
  - `manual` — explicitly human (`Approve?:`-style / "by inspection") or a command with unresolved placeholders.
- Descriptor: `{fr_id, kind, command_argv|None, assertion_text, reason}`.
- **Deps:** none (parallel with FR-1).

### FR-5 — `startd8 navigator verify` + opt-in evaluate  *(revised by D-3, D-6)*
- New `@navigator_app.command("verify")` in `cli_navigator.py`; `--requirements <doc>`, `--run-oracle` (default OFF), `--format json|html`.
- Default inert: every descriptor → `skip`, **no subprocess**.
- `--run-oracle`: for `command`-kind only, run `command_argv` via `subprocess.run(argv, shell=False, timeout=…)`
  with **no network** and a **verb allow-list** (only `startd8 …`; refuse anything else → `skip`, reason
  "non-allowlisted verb"). **pass = exit 0 of the extracted command; fail = non-zero.** The prose
  `assertion_text` is *not* asserted by the run — it is emitted alongside as the human-checkable residue.
- **Self-exec guard:** refuse to run a command that is itself `startd8 navigator verify … --run-oracle`
  (prevents recursion when a Verify clause cites the verify command).
- Aggregate exit code (REQ FR-5 v0.1.1): 0 when no `fail`, non-zero iff any `fail`.
- **Deps:** FR-4.

### FR-6 — `pipeline_provenance()` in `provenance.py`  *(revised by D-4)*
- Add `pipeline_provenance(nodes, stages)` **beside** `chrome_provenance` (same module — Mottainai).
- Row schema: `{element, stage, origin, value, present}` — keeps `value` for parity with the sibling,
  adds `stage`. (v0.1 said "same element→origin→value shape"; it's a sibling schema, now stated so.)
- For a given FR (or a `Touches`/`Lives` file): walk artifact → the stage whose `sdk_artifact`/kind owns it
  → … → the requirement, emitting an ordered chain whose stage ordinals are a subsequence of FR-1's.
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
