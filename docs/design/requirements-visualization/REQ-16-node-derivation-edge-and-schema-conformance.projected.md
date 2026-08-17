<!-- GENERATED det-plan/0.1 — projected $0 from the paired det-req by startd8 plan_codegen; do not edit by hand -->

# SDK navigator types a derivation edge on the Node so the prose-to-product compilation chain is traceable without heuristic reconstruction, and adds a schema self-conformance gate asserting the Node code matches its documented field set and status-derivation agrees across implementations. — Implementation Plan (det-plan/0.1)

- **version:** 0.1
- **formatVersion:** det-plan/0.1
- **pairsWith:** `REQ-16-node-derivation-edge-and-schema-conformance.md`
- **companionKind:** PLAN
- **maturity:** 0.1
- **handle:** `plan/sdk-navigator-types-a-derivation-edge-on-the-9d994bb0`
- **ref:** `cc:intent:requirements-visualization:plan:req-16`

> A **det-plan is a `$0` projection of a det-req** — this document is derived, never authored. Its FR grouping and ordering are the requirement's authored structure; the strategic build-ordering strategy is the human's to add (the human-gated residue).

## Iterations

_4 iteration(s); costClass rollup: 4 llm-integration._

### F-1 — The Node types a first-class derivation edge object distinct from containment reserving an optional regime slot so the compilation chain is read not reconstructed

- **FRs:** FR-1
- **targetFiles:** `src/startd8/navigator/models.py`, `src/startd8/navigator/provenance.py`, `tests/unit/navigator/test_provenance.py`
- **dependsOn:** — (no authored dependency)
- **costClass:** llm-integration
- **status:** planned
- **gate (from the FRs' `Verify:`):**
  - FR-1: a node with a derivation input exposes it as a typed edge object distinct from its `children` (carrying an optional `regime` slot that is unset in this REQ), and `pipeline_provenance` returns a chain sourced from that edge (not the longest-prefix heuristic)

### F-2 — A conformance test asserts the Node code field set equals its documented field manifest and fails on un-mirrored drift

- **FRs:** FR-2
- **targetFiles:** `src/startd8/navigator/models.py`, `tests/unit/navigator/test_schema_conformance.py`
- **dependsOn:** — (no authored dependency)
- **costClass:** llm-integration
- **status:** planned
- **gate (from the FRs' `Verify:`):**
  - FR-2: current `node_field_names()` equals the manifest; a test that adds a synthetic field without manifesting it fails with a named drift message

### F-3 — A shared fixture set proves the SDK status classifiers agree and is exported as a portable cross-repo contract

- **FRs:** FR-3
- **targetFiles:** `tests/unit/navigator/fixtures/status_contract.json`, `tests/unit/navigator/test_status_agreement.py`
- **dependsOn:** — (no authored dependency)
- **costClass:** llm-integration
- **status:** planned
- **gate (from the FRs' `Verify:`):**
  - FR-3: every fixture yields the same gap-class across the SDK classifiers; the exported `status_contract.json` is a self-contained file (no SDK import) a second implementation can run against

### F-4 — The derivation edge and conformance gates leave the render and app-scaffold path byte-identical with only the schema golden changing

- **FRs:** FR-4
- **targetFiles:** `tests/unit/navigator/test_schema_conformance.py`, `tests/unit/wireframe/test_render_profile.py`
- **dependsOn:** — (no authored dependency)
- **costClass:** llm-integration
- **status:** planned
- **gate (from the FRs' `Verify:`):**
  - FR-4: `test_no_profile_is_byte_identical` passes unedited; the `node_field_names()` golden delta is exactly the typed derivation edge (plus, when the ADR lands, `verify`/`approve`/`was`) and nothing else

## Dependencies (the iteration DAG)

- — no authored `Depends:` edges; iterations are independent by the requirement's declared topology (ordering is the human-gated residue).

## Reuse / phantom audit (§4)

- `src/startd8/navigator/models.py` — ✓ resolves
- `src/startd8/navigator/provenance.py` — ✓ resolves
- `tests/unit/navigator/test_provenance.py` — ✗ PHANTOM (absent on disk)
- `tests/unit/navigator/test_schema_conformance.py` — ✓ resolves
- `tests/unit/navigator/test_status_agreement.py` — ✓ resolves
- `tests/unit/navigator/fixtures/status_contract.json` — ✓ resolves
- `tests/unit/wireframe/test_render_profile.py` — ✓ resolves

## Verify (whole change) — the FR `Verify:` rollup (§5)

- FR-1: a node with a derivation input exposes it as a typed edge object distinct from its `children` (carrying an optional `regime` slot that is unset in this REQ), and `pipeline_provenance` returns a chain sourced from that edge (not the longest-prefix heuristic)
- FR-2: current `node_field_names()` equals the manifest; a test that adds a synthetic field without manifesting it fails with a named drift message
- FR-3: every fixture yields the same gap-class across the SDK classifiers; the exported `status_contract.json` is a self-contained file (no SDK import) a second implementation can run against
- FR-4: `test_no_profile_is_byte_identical` passes unedited; the `node_field_names()` golden delta is exactly the typed derivation edge (plus, when the ADR lands, `verify`/`approve`/`was`) and nothing else

_det-plan/0.1 — projected `$0` from the paired det-req; maturity `0.1` (un-hardened). The projector owns the format's derived fields; the ordering strategy is the human-gated residue._
