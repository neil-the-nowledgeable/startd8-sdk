<!-- GENERATED det-plan/0.1 — projected $0 from the paired det-req by startd8 plan_codegen; do not edit by hand -->

# SDK navigator promotes the acceptance oracle, human-approval gate, and change-history from parsed det-req fields into first-class Node fields so the requirements-to-Node projection carries the reliability semantics instead of dropping them, bumping the schema to 0.4.0 while the render stays byte-identical. — Implementation Plan (det-plan/0.1)

- **version:** 0.1
- **formatVersion:** det-plan/0.1
- **pairsWith:** `REQ-17-promote-oracle-gate-history-to-node-fields.md`
- **companionKind:** PLAN
- **maturity:** 0.1
- **handle:** `plan/sdk-navigator-promotes-the-acceptance-oracle-6fb6c312`
- **ref:** `cc:intent:requirements-visualization:plan:req-17`

> A **det-plan is a `$0` projection of a det-req** — this document is derived, never authored. Its FR grouping and ordering are the requirement's authored structure; the strategic build-ordering strategy is the human's to add (the human-gated residue).

## Iterations

_4 iteration(s); costClass rollup: 4 llm-integration._

### F-1 — The Node model gains optional empty-default verify approve and was fields carrying the acceptance oracle human gate and change history

- **FRs:** FR-1
- **targetFiles:** `src/startd8/navigator/models.py`, `tests/unit/navigator/test_schema_conformance.py`
- **dependsOn:** — (no authored dependency)
- **costClass:** llm-integration
- **status:** planned
- **gate (from the FRs' `Verify:`):**
  - FR-1: `models.Node()` constructs with `verify`/`approve`/`was` defaulting empty, and `node_field_names()` contains all three

### F-2 — The requirements source projects each FR parsed verify approve and was onto the Node instead of dropping them at the boundary

- **FRs:** FR-2
- **targetFiles:** `src/startd8/navigator/sources_requirements.py`, `tests/unit/navigator/test_sources_and_cli.py`
- **dependsOn:** — (no authored dependency)
- **costClass:** llm-integration
- **status:** planned
- **gate (from the FRs' `Verify:`):**
  - FR-2: projecting an FR that has `Verify:`/`Approve?:`/`

### F-3 — The three promoted fields register in the REQ-16 conformance manifest so the parity gate covers them

- **FRs:** FR-3
- **targetFiles:** `src/startd8/navigator/models.py`, `tests/unit/navigator/test_schema_conformance.py`
- **dependsOn:** — (no authored dependency)
- **costClass:** llm-integration
- **status:** planned
- **gate (from the FRs' `Verify:`):**
  - FR-3: the conformance manifest lists `verify`/`approve`/`was`; removing one from the manifest while it exists in code fails the parity test with a named drift message

### F-4 — The promotion leaves the render byte-identical with a single node-field-names golden delta co-churned with REQ-16

- **FRs:** FR-4
- **targetFiles:** `tests/unit/navigator/test_schema_conformance.py`, `tests/unit/wireframe/test_render_profile.py`
- **dependsOn:** — (no authored dependency)
- **costClass:** llm-integration
- **status:** planned
- **gate (from the FRs' `Verify:`):**
  - FR-4: `test_no_profile_is_byte_identical` passes unedited; the `node_field_names()` golden delta is exactly `{verify, approve, was}` plus REQ-16's derivation edge and nothing else

## Dependencies (the iteration DAG)

- — no authored `Depends:` edges; iterations are independent by the requirement's declared topology (ordering is the human-gated residue).

## Reuse / phantom audit (§4)

- `src/startd8/navigator/models.py` — ✓ resolves
- `tests/unit/navigator/test_schema_conformance.py` — ✓ resolves
- `src/startd8/navigator/sources_requirements.py` — ✓ resolves
- `tests/unit/navigator/test_sources_and_cli.py` — ✓ resolves
- `tests/unit/wireframe/test_render_profile.py` — ✓ resolves

## Verify (whole change) — the FR `Verify:` rollup (§5)

- FR-1: `models.Node()` constructs with `verify`/`approve`/`was` defaulting empty, and `node_field_names()` contains all three
- FR-2: projecting an FR that has `Verify:`/`Approve?:`/`
- FR-3: the conformance manifest lists `verify`/`approve`/`was`; removing one from the manifest while it exists in code fails the parity test with a named drift message
- FR-4: `test_no_profile_is_byte_identical` passes unedited; the `node_field_names()` golden delta is exactly `{verify, approve, was}` plus REQ-16's derivation edge and nothing else

_det-plan/0.1 — projected `$0` from the paired det-req; maturity `0.1` (un-hardened). The projector owns the format's derived fields; the ordering strategy is the human-gated residue._
