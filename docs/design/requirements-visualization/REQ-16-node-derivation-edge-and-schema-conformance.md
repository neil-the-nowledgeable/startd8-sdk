# Node Derivation Edge + Schema Self-Conformance — Requirements

**Project:** startd8-sdk   **Criticality:** high
**Version:** 0.1   **Date:** 2026-08-16
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** *(plan deferred — spec-only; delivered via the Spec Delivery Loop)* · `ADR_promote-oracle-and-human-gate-into-node-ir.md` (sibling schema evolution) · `dev-os/NODE-SCHEMA.md` (the IR spec this gates) · the NLPS thesis `~/Documents/craft/THE_NATURAL_LANGUAGE_PROGRAMMING_SYSTEM.md`
**Inherits standards:** det-req-kit · NODE-SCHEMA v0.3.9 · NAMING_CONVENTION · REQ-08 (pipeline provenance — the heuristic this replaces)
**Audience:** operator / SDK contributors / cross-repo Node adopters (ContextCore · dev-os)
**Trust boundary:** local repo, read-only; no network; no LLM
**Data classification:** internal

> **Readable handle:** `feature/sdk-navigator-types-a-derivation-edge-on-the-9d994bb0`
> **Semantic name:** *SDK navigator types a derivation edge on the Node so the prose-to-product compilation chain is traceable without heuristic reconstruction, and adds a schema self-conformance gate asserting the Node code matches its documented field set and status-derivation agrees across implementations.*
> **Canonical ref:** `cc:intent:requirements-visualization:feature:req-16`

## 0. Why this exists — make the IR's compilation chain native, and gate its drift

The NLPS is a compiler whose IR is the Node; its essence is **derivation** (intent → FR → contract →
impl → test → doc). Yet the Node's only native edge is **containment** (`children` = drill), plus a
generic **reference** edge (`child_keys`, which REQ-08 used for stage DEPENDS-ON). There is no
*typed* derivation relation — so REQ-08's `pipeline_provenance` must **reconstruct** the chain
heuristically (longest-prefix ownership) rather than read it. Type one derivation edge and the
compilation chain becomes traceable **by construction** (Mieruka), not by heuristic.

Second, the IR spec has **silently drifted from its code**: `NODE-SCHEMA.md` §1 lists ten fields but
`models.Node` carries fifteen — §1 omits `category/orientation/status_facets/child_keys/attributes`.
Nothing gates that drift, and the status-derivation *function* is forked across ≥3 implementations
(`models.derive_status`, `det-req-kit/extract.py`, Studio `req-health.mjs`) with no shared-fixture
agreement check — an IR-semantics drift risk (the seat spec's R1-F2 already flagged the SDK twin as
the untested deciding implementation). This REQ adds the **self-conformance gate**: the schema-as-Node
asserts its own field parity and status agreement.

## Overview

Type a **derivation edge** on the Node (distinct from containment `children`) so `pipeline_provenance`
reads the compilation chain instead of reconstructing it. Add a **field-parity conformance test** (the
Node code's field set equals a canonical documented manifest — the drift that left §1 stale fails it),
and a **status-derivation agreement test** (a shared fixture set yields the same gap-class across the
SDK implementations, exported as a portable contract dev-os / Studio can adopt). All SDK-side and
additive; the render output + app-scaffold path stay byte-identical; the `node_field_names()` /
schema golden change is the deliberate, reviewed schema-evolution signal (coordinated with the ADR).

## Design decision — OQ-6 resolved (2026-08-16): realization rides the derivation EDGE

The realization regime (`deterministic | llm | human`, see the RESEARCH note) is a property of the
**transform**, not the artifact — it is the *derivation* that is deterministic or stochastic, not the
node it produces. Decision (schema-owner lean, confirmed as the more cohesive model): **realization is
carried on the derivation edge**, and a node's realization facet is **DERIVED from its incoming edges**
(min-rolls-up, exactly like `status` is derived, not stored). This unlocks more cohesion:
- **One construct, not two** — the derivation edge and the realization facet fuse into a single typed edge
  (`from` + relation + `regime` + provenance) instead of an edge *plus* a separate node facet.
- **Edge-shaped provenance is a 1:1 lift** — Kaizen/`ai_layer`/`costs` already stamp per-*generation-event*
  metadata (model/prompt/cost/seed); a generation event **is** a transform, so it maps onto the edge natively.
- **Mixed realization is native** — a node scaffolded deterministically then LLM-filled has two edges of
  differing `regime`; no `hybrid` node value, no rollup hack.
- **Invariant 9 becomes an edge rule** — a *stochastic edge* obligates its target node to a passing `verify`.

**This REQ only RESERVES the `regime` slot** (FR-1, unset); populating it + deriving node realization +
the determinism-% rollup is the later realization REQ (NR-6). Reserving now means that REQ *fills a slot*
rather than adding a parallel facet — the cohesion payoff.

## Objectives

- **O-1:** Type one derivation edge so the compilation chain is traceable without heuristic reconstruction — target: `pipeline_provenance` reads the typed edge; a node exposes its derivation inputs distinctly from its containment children.
- **O-2:** Gate schema self-conformance — target: a test fails when a Node field is added in code without updating the documented field manifest (catching the current §1 staleness class).
- **O-3:** Converge status-derivation — target: a shared fixture set yields identical gap-class across the SDK's implementations, exported as a portable contract for the cross-repo twins.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| scope | Building a general graph-relation system instead of typing ONE edge | NR-4: type exactly one derivation relation; no general edge-kind framework (anti-over-abstraction) | high |
| scope | Editing the cross-repo NODE-SCHEMA.md / ContextCore mirror without the schema owner's go | NR-1: SDK-side only + a portable contract; the dev-os doc + mirror updates are the coordinated cross-repo follow-up | high |
| quality | The conformance test couples to a dev-os file path and breaks in an SDK-only checkout | FR-2: parity is asserted against a canonical manifest **inside the SDK**; the dev-os doc parity is a separate, existence-guarded cross-repo check | medium |
| quality | Confusing this REQ's edge work with the ADR's field promotions | NR-2: this REQ does NOT implement `verify`/`approve`/`was`; it provides the gate that will enforce them | medium |

## Functional requirements

- **FR-1 — Typed derivation edge (a first-class edge object, regime-ready).** Distinguish a Node's **derivation inputs** (the upstream keys it was derived/compiled from) from its containment `children` via a **first-class typed edge object** (`from`-key + relation kind) that reserves an OPTIONAL, currently-unset `regime` slot for edge-carried realization (per the OQ-6 decision below), so `pipeline_provenance` reads the derivation chain from the typed edge instead of longest-prefix ownership. Name: The Node types a first-class derivation edge object distinct from containment reserving an optional regime slot so the compilation chain is read not reconstructed. Touches: `src/startd8/navigator/models.py`, `src/startd8/navigator/provenance.py`, `tests/unit/navigator/test_provenance.py`. Lives: code src/startd8/navigator/models.py. Approve?: is the derivation edge a first-class object distinct from containment children with a reserved regime slot?. Verify: a node with a derivation input exposes it as a typed edge object distinct from its `children` (carrying an optional `regime` slot that is unset in this REQ), and `pipeline_provenance` returns a chain sourced from that edge (not the longest-prefix heuristic). Serves: O-1
- **FR-2 — Schema field-parity conformance.** Add a test asserting `models.Node`'s field set equals a canonical documented field manifest (the schema-as-Node self-check); adding a Node field in code without updating the manifest fails the test — the drift class that left `NODE-SCHEMA.md` §1 stale. Name: A conformance test asserts the Node code field set equals its documented field manifest and fails on un-mirrored drift. Touches: `src/startd8/navigator/models.py`, `tests/unit/navigator/test_schema_conformance.py`. Lives: test tests/unit/navigator/test_schema_conformance.py. Approve?: does adding an un-manifested Node field fail the parity test?. Verify: current `node_field_names()` equals the manifest; a test that adds a synthetic field without manifesting it fails with a named drift message. Serves: O-2
- **FR-3 — Status-derivation agreement (SDK-side + portable contract).** A shared fixture set runs through the SDK's status/gap classifiers (`models.derive_status` and `det_req`'s gap classifier) asserting identical class per fixture, and the fixture set is exported as a portable contract file the cross-repo twins (`extract.py`, `req-health.mjs`) can adopt. Name: A shared fixture set proves the SDK status classifiers agree and is exported as a portable cross-repo contract. Touches: `tests/unit/navigator/test_status_agreement.py`, `tests/unit/navigator/fixtures/status_contract.json`. Lives: test tests/unit/navigator/test_status_agreement.py. Approve?: do the SDK status classifiers agree per fixture, with the fixtures exported as a contract?. Verify: every fixture yields the same gap-class across the SDK classifiers; the exported `status_contract.json` is a self-contained file (no SDK import) a second implementation can run against. Serves: O-3
- **FR-4 — Additive, render byte-identical.** The derivation edge + conformance tests are additive: the render output and the app-scaffold wireframe path are byte-identical; the only golden change is `node_field_names()` / the schema field manifest — the deliberate, reviewed schema-evolution signal (coordinated with the ADR's field promotions). Name: The derivation edge and conformance gates leave the render and app-scaffold path byte-identical with only the schema golden changing. Touches: `tests/unit/wireframe/test_render_profile.py`, `tests/unit/navigator/test_schema_conformance.py`. Lives: test tests/unit/wireframe/test_render_profile.py. Approve?: is the render byte-identical, with only the schema golden as the intended change?. Verify: `test_no_profile_is_byte_identical` passes unedited; the `node_field_names()` golden delta is exactly the typed derivation edge (plus, when the ADR lands, `verify`/`approve`/`was`) and nothing else. Serves: O-1, O-2

## Non-requirements

- **NR-1:** Does **NOT** edit `dev-os/NODE-SCHEMA.md` or the ContextCore Node mirror — those cross-repo updates need the schema owner's go and are the coordinated Yokoten follow-up. This REQ is SDK-side + a portable contract.
- **NR-2:** Does **NOT** implement the ADR's field promotions (`verify`/`approve`/`was`) — that is the ADR's own delivery. This REQ provides the conformance gate that will *enforce* them (FR-2's manifest is where they register).
- **NR-3:** Does **NOT** force `extract.py` / `req-health.mjs` to adopt the status contract — SDK-side agreement + a portable fixture file only; cross-repo adoption is the follow-up.
- **NR-4:** Does **NOT** build a general edge-kind / graph-relation framework — exactly one derivation relation is typed (anti-over-abstraction; the schema's own "simplification not accretion" bar).
- **NR-5:** Does **NOT** replace `children` — containment drill is unchanged; the derivation edge is a distinct, additive relation.
- **NR-6:** Does **NOT** populate the edge's `regime` slot, derive node realization, or compute the determinism-% rollup — this REQ only *reserves* the slot (FR-1); filling it is the later realization REQ (per the OQ-6 decision). This keeps REQ-16's scope to structure + conformance while making it forward-compatible.
