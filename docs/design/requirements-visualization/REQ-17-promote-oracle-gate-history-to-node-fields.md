# Promote Oracle + Human-Gate + Change-History to Node Fields — Requirements

**Project:** startd8-sdk   **Criticality:** high
**Version:** 0.1   **Date:** 2026-08-16
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** *(plan deferred — spec-only; delivered via the Spec Delivery Loop)* · **`ADR_promote-oracle-and-human-gate-into-node-ir.md` (ACCEPTED 2026-08-16 — this REQ implements it)** · `REQ-16` (co-delivered in the same 0.4.0 schema bump) · `REQ-08` (the oracle consumer)
**Inherits standards:** det-req-kit · NODE-SCHEMA v0.3.9→**0.4.0** · NAMING_CONVENTION · REQ-16 (schema conformance gate)
**Audience:** operator / SDK contributors / cross-repo Node adopters (ContextCore · dev-os)
**Trust boundary:** local repo, read-only projection; no network; no LLM
**Data classification:** internal

> **Readable handle:** `feature/sdk-navigator-promotes-the-acceptance-oracle-6fb6c312`
> **Semantic name:** *SDK navigator promotes the acceptance oracle, human-approval gate, and change-history from parsed det-req fields into first-class Node fields so the requirements-to-Node projection carries the reliability semantics instead of dropping them, bumping the schema to 0.4.0 while the render stays byte-identical.*
> **Canonical ref:** `cc:intent:requirements-visualization:feature:req-17`

## 0. Why this exists — carry the reliability semantics, don't reconstruct them

The ADR (accepted) established the finding: `det_req.py` parses each FR into
`{name, lives, verify, approve_prompts, was, …}`, but `models.Node` has **no** `verify`, `approve`, or
`was` — so the acceptance **oracle**, the human-approval **gate**, and the **change-history** are dropped
at the `det_req→Node` boundary, forcing REQ-08 to reconstruct them heuristically. In the NLPS the oracle
is the compiler's type-checker and the human-gate is the reliability pivot; the IR must **carry** them.

This REQ is the ADR's implementation vehicle (REQ-16's NR-2 deliberately excluded it). It lands the three
fields and wires the projection to carry them — a **Node schema-version bump (0.3.9 → 0.4.0)** whose only
intended change is the `node_field_names()` golden; the render stays byte-identical. It does **not** add
enforcement (invariant 9) or oracle classification — it lands the fields those later steps reference.

## Overview

Add `verify`, `approve`, `was` as optional, empty-default fields on `models.Node`; wire
`sources_requirements` to project each FR's parsed `verify` / `approve_prompts` / `was` onto them instead
of dropping them; register the three in REQ-16's conformance manifest so they can't be added un-mirrored;
keep the render + app-scaffold path byte-identical (only the schema golden changes, co-churned once with
REQ-16). The three are carried as parsed (raw clause / list / string) — **oracle classification stays
REQ-08's job** and the invariant-9 verification obligation stays the realization REQ's job (NR-1/NR-2).

## Objectives

- **O-1:** The Node carries the reliability fields — target: `models.Node` gains `verify`/`approve`/`was` (optional, empty-default); `node_field_names()` includes them; schema is 0.4.0.
- **O-2:** The requirements projection carries them, not drops them — target: an FR with `Verify:`/`Approve?:`/`Was:` yields a Node whose fields hold those values; an FR without them yields empty defaults (byte-identical).
- **O-3:** The promotion is gated + byte-identical — target: the three register in REQ-16's conformance manifest; `test_no_profile_is_byte_identical` passes unedited; the only golden delta is `node_field_names()`.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| scope | Sliding into oracle classification (command/assertion/manual) or invariant-9 enforcement | NR-1/NR-2: carry the parsed values only; classification = REQ-08, enforcement = the realization REQ | high |
| quality | The new fields leak into the render and break byte-identity | O-3/FR-4: fields are empty-default and not rendered; `test_no_profile_is_byte_identical` is the oracle | high |
| coordination | The `node_field_names()` golden churns twice (once here, once for REQ-16's edge) | FR-4: co-deliver with REQ-16 in ONE 0.4.0 bump — a single reviewed golden delta | medium |
| coordination | dev-os `NODE-SCHEMA.md` §1 + ContextCore mirror drift from the new fields | NR-3: cross-repo follow-up (authorized by the ADR go, separate handoff); REQ-16's parity gate flags it | medium |

## Functional requirements

- **FR-1 — Add the three reliability fields to the Node.** `models.Node` gains `verify` (the acceptance oracle — the FR's Verify clause), `approve` (the human-approval gate — the FR's Approve prompt), and `was` (the change-history alias — the FR's Was value), all optional with empty defaults; `node_field_names()` includes them (the deliberate 0.4.0 signal). Name: The Node model gains optional empty-default verify approve and was fields carrying the acceptance oracle human gate and change history. Touches: `src/startd8/navigator/models.py`, `tests/unit/navigator/test_schema_conformance.py`. Lives: code src/startd8/navigator/models.py. Approve?: does the Node carry verify/approve/was as optional empty-default fields?. Verify: `models.Node()` constructs with `verify`/`approve`/`was` defaulting empty, and `node_field_names()` contains all three. Serves: O-1
- **FR-2 — The requirements projection carries them, not drops them.** `sources_requirements` projects each parsed FR's `verify` / `approve_prompts` / `was` onto the Node's new fields instead of discarding them at the boundary; an FR lacking a clause projects the empty default. Name: The requirements source projects each FR parsed verify approve and was onto the Node instead of dropping them at the boundary. Touches: `src/startd8/navigator/sources_requirements.py`, `tests/unit/navigator/test_sources_and_cli.py`. Lives: code src/startd8/navigator/sources_requirements.py. Approve?: does projecting an FR carry its Verify/Approve/Was onto the Node?. Verify: projecting an FR that has `Verify:`/`Approve?:`/`Was:` yields a Node whose `verify`/`approve`/`was` equal those parsed values; an FR without them yields empty fields. Serves: O-2
- **FR-3 — Register the fields in the conformance manifest.** The three fields register in REQ-16's canonical field manifest so the parity gate (REQ-16 FR-2) fails if any is present in code but absent from the manifest — closing the drift class that left `NODE-SCHEMA.md` §1 stale. Name: The three promoted fields register in the REQ-16 conformance manifest so the parity gate covers them. Touches: `tests/unit/navigator/test_schema_conformance.py`, `src/startd8/navigator/models.py`. Lives: test tests/unit/navigator/test_schema_conformance.py. Approve?: are verify/approve/was covered by the field-parity gate?. Verify: the conformance manifest lists `verify`/`approve`/`was`; removing one from the manifest while it exists in code fails the parity test with a named drift message. Serves: O-1, O-3
- **FR-4 — Byte-identical render, single co-churned golden.** The promotion is additive to the render: `test_no_profile_is_byte_identical` passes unedited and the only golden delta is `node_field_names()`, co-delivered with REQ-16's derivation edge as ONE reviewed 0.4.0 schema bump. Name: The promotion leaves the render byte-identical with a single node-field-names golden delta co-churned with REQ-16. Touches: `tests/unit/wireframe/test_render_profile.py`, `tests/unit/navigator/test_schema_conformance.py`. Lives: test tests/unit/wireframe/test_render_profile.py. Approve?: is the render byte-identical with only one coordinated schema golden change?. Verify: `test_no_profile_is_byte_identical` passes unedited; the `node_field_names()` golden delta is exactly `{verify, approve, was}` plus REQ-16's derivation edge and nothing else. Serves: O-3

## Non-requirements

- **NR-1:** Does **NOT** implement invariant 9 (the `realization:llm ⇒ verify-required` / `human ⇒ approve` obligation) — this REQ lands the fields that later obligation references; enforcement is the realization REQ.
- **NR-2:** Does **NOT** classify the oracle (`command` / `assertion` / `manual`) — `verify` carries the raw clause, structured-ready; classification is REQ-08's `verify_oracle`.
- **NR-3:** Does **NOT** edit `dev-os/NODE-SCHEMA.md` §1 or the ContextCore Node mirror — cross-repo updates are authorized by the accepted ADR but land as a separate coordinated handoff; REQ-16's parity gate flags the drift until they follow.
- **NR-4:** The fields are OPTIONAL / empty-default — a non-requirements Node (capability / signal / case-section) with no oracle carries empty values and renders unchanged.
- **NR-5:** Does **NOT** touch `children` / `child_keys` / the derivation edge — that is REQ-16's surface (co-delivered, not merged into this REQ).
