# Realization Regime + Determinism Rollup (approach (a), (b)-ready seam) — Requirements

**Project:** startd8-sdk   **Criticality:** high
**Version:** 0.1   **Date:** 2026-08-16
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** *(plan deferred — spec-only; delivered via the Spec Delivery Loop)* · `RESEARCH_llm-interpreter-backend-and-realization-facet.md` (the design + OQ-1..6) · `REQ-16` (the derivation edge + reserved `regime` slot this fills) · `REQ-17` (the `verify` field invariant 9 references) · `ADR_promote-oracle-and-human-gate-into-node-ir.md`
**Inherits standards:** det-req-kit · NODE-SCHEMA v0.4.0 · NAMING_CONVENTION · REQ-06 (govern — the enforcement home) · REQ-16/REQ-17
**Audience:** operator / SDK contributors / cross-repo Node adopters
**Trust boundary:** local repo, read-only; no network; no LLM; **(a) reads no construction internals**
**Data classification:** internal

> **Readable handle:** `feature/sdk-navigator-derives-each-node-s-realization-806ad01e`
> **Semantic name:** *SDK navigator derives each node's realization regime (deterministic, llm, or human) from its incoming derivation edges, rolls it up to a determinism-% at the summary altitude, and enforces the verify obligation — through a confidence-aware provenance seam that ships declared regime first and is ready to ground in measured construction provenance.*
> **Canonical ref:** `cc:intent:requirements-visualization:feature:req-18`

## 0. Why this exists — the IR's last ungrounded facet, made honest and (b)-ready

The IR now expresses HOW each node was realized only implicitly. This REQ fills REQ-16's reserved
`regime` slot so the IR states, per node, **which of the two back-ends produced it** (the deterministic
`$0` compiler vs the LLM interpreter) or that it is human-authored — and rolls that up to a **determinism-%**,
the SDK's headline cost/reliability number, made IR-derived instead of narrated. It also enforces
**invariant 9** (a stochastic edge obligates its target's `verify`), completing the "how do I trust this
node?" ledger.

**The goal is (b): a *measured* determinism-%, grounded in real construction provenance.** But grounding a
number wrongly is worse than declaring it (false grounding is a lie the system trusts), so this REQ ships
**approach (a) first — a *declared* regime — through a confidence-aware provenance seam** that is the
integrity firewall: the navigator reads regime from an OPTIONAL provenance source and, when that source is
absent or its match confidence is low, **degrades to the declared value (or `unknown`) — never asserting a
measurement it cannot ground.** (a) proves the whole machine (derive → roll up → enforce) end-to-end on
declared regimes and yields the insights that make (b) more integrous; (b) then fills the seam without a
rewrite. The seam keeps the navigator depending on a **stable contract**, never on construction internals.

## Design decision — (a) is the first iteration OF (b), not an alternative

Realization is the one node facet that would be *asserted* in a grounding-first IR (invariant 4). (b) —
lifting the *measured* regime from the scattered construction provenance (`micro_prime` registry model/
strategy, `prime-result`, `$0`-skip decisions) and joining it to `Node.lives.ref` by file path — is the
move that brings it up to the system's own standard, adds **self-monitoring** (planned-vs-realized
determinism regressions become visible), and feeds the RETROSPECTIVE bookend. This REQ is scoped to (a) +
the seam; **(b) is the named, additive follow-on** (NR-1/NR-2). The seam's confidence-aware degradation is
built here so (b) *cannot* introduce false grounding.

## Overview

Populate the derivation edge's `regime` (declared: `deterministic|llm|human`, default `unknown`); add
`derive_realization(node)` that reads regime **through a confidence-aware seam** (absent/low-confidence →
declared/`unknown`) and returns the **distribution** over a node's subtree (derived, not stored — like
`status`); render a determinism-% summary line (labeled **declared** until (b) grounds it); enforce
invariant 9 as an activation-gated `govern` check; expose `realization` as a derived §3a facet. All
additive and byte-identical; no construction subsystem is touched.

## Objectives

- **O-1:** Each node's realization is derived from its edges and rolled to a determinism-% — declared in (a), through a seam ready to ground in (b) — target: `derive_realization` returns a per-subtree regime distribution; the summary renders a determinism-% labeled `declared`.
- **O-2:** The verify obligation (invariant 9) is enforced honestly — target: an `llm`-regime edge to a realized node with an empty `verify` is a named `govern` finding; unbuilt/spec nodes never fail.
- **O-3:** Additive, byte-identical, and (b)-ready — target: existing domain renders are byte-identical; the seam is the modularity firewall + honest-degradation contract; no import from construction subsystems.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| quality | (b) later grounds a regime on a wrong file↔requirement join → a confidently-wrong determinism-% (false grounding) | FR-2: the seam is confidence-aware from day one — absent/low-confidence provenance degrades to declared/`unknown`, never asserts a low-confidence measurement | high |
| scope | (a) sliding into construction-provenance wiring (that is (b)) | NR-1/NR-2: (a) is navigator-internal + declared; the seam is unwired; no import from `backend_codegen`/`contractors`/`micro_prime` | high |
| quality | A declared determinism-% read as if measured | FR-4: the summary line is explicitly labeled `declared` until a provenance source is wired (b) | high |
| scope | Building a planned-vs-realized delta or a general facet framework | NR-3/NR-4: single declared regime (OQ-1 is (b)'s payoff); one derived facet on the existing §3a mechanism | medium |
| dependency | The `regime` slot / edges are on branch `feature/req-16-17-node-schema-bump` (aaa39178), not yet on `main` | NR-5: spec-ready now; build-blocked until REQ-16/17 land on `main` | high |

## Functional requirements

- **FR-1 — Declared regime on the derivation edge.** Populate REQ-16's reserved edge `regime` slot from a declared value on the pipeline/base definitions — one of `deterministic` / `llm` / `human`, defaulting to `unknown` when unspecified; in approach (a) this is authored (declared), not measured. Name: The derivation edge carries a declared realization regime of deterministic llm human or unknown. Touches: `src/startd8/navigator/models.py`, `src/startd8/navigator/view_definition.py`, `tests/unit/navigator/test_view_definition.py`. Lives: code src/startd8/navigator/models.py. Approve?: does a derivation edge carry a declared regime defaulting to unknown?. Verify: a pipeline stage's implementation edge declared `deterministic` reads back `deterministic`, and an edge with no declared regime reads `unknown`. Serves: O-1
- **FR-2 — Confidence-aware provenance seam (the (b)-ready firewall).** Add `derive_realization` that reads an edge's regime through a stable typed seam consulting an OPTIONAL provenance source; when the source is absent OR its match confidence is below a threshold, it degrades to the declared regime (or `unknown`) and never asserts the low-confidence value; in (a) no source is wired so the declared value always stands. Name: A confidence-aware seam reads regime from an optional provenance source and degrades to the declared value when absent or low-confidence. Touches: `src/startd8/navigator/realization.py`, `tests/unit/navigator/test_realization.py`. Lives: code src/startd8/navigator/realization.py. Approve?: does the seam degrade to declared or unknown rather than assert a low-confidence measurement?. Verify: with no provenance source `derive_realization` returns the declared regime; a stub low-confidence provenance match degrades to declared/`unknown` and never overrides with the low-confidence value. Serves: O-1, O-3
- **FR-3 — Derive node realization from incoming edges (a distribution).** `derive_realization(node)` returns the DISTRIBUTION of regimes over the node's subtree — a leaf yields its edge's single regime, a parent yields the aggregate counts — derived not stored (like `status`), and NOT a min-rollup (realization is a spread, not a worst-case). Name: The node realization is derived from incoming edges as a regime distribution over the subtree not a min-rollup. Touches: `src/startd8/navigator/realization.py`, `tests/unit/navigator/test_realization.py`. Lives: code src/startd8/navigator/realization.py. Approve?: is node realization a derived distribution over the subtree rather than a stored scalar?. Verify: a leaf returns its single edge regime; a parent over two deterministic and one llm leaf returns the distribution `{deterministic: 2, llm: 1}`. Serves: O-1
- **FR-4 — Determinism-% summary line, honestly labeled.** The summary altitude gains a realization line rolling the distribution to a headline determinism-% (e.g. `28 deterministic / 3 llm / 0 human — 90% $0`), deterministic and speakable (SV-7), and explicitly labeled `declared` until a provenance source is wired ((b) relabels it `measured`). Name: The summary renders a determinism-% from the regime distribution labeled declared until provenance grounds it. Touches: `src/startd8/wireframe_view/compose.py`, `tests/unit/wireframe/test_render_profile.py`. Lives: code src/startd8/wireframe_view/compose.py. Approve?: does the summary show the regime distribution and a determinism-% labeled declared?. Verify: a fixture graph with declared regimes renders the distribution plus a determinism-% carrying the word `declared`; a graph with no regime data renders no determinism-% line. Serves: O-1
- **FR-5 — Invariant 9 enforcement, activation-gated.** A `govern` check where an edge with `regime == llm` obligates its target node's `verify` field to be non-empty, firing only once the node's `lives` evidence is non-empty (mirroring the ships_when-vs-lives invariant) so unbuilt/spec nodes never fail; a violation is a named finding, never a crash. Name: A govern check obligates an llm-regime edge's target to a non-empty verify only once its lives evidence is present. Touches: `src/startd8/navigator/govern.py`, `tests/unit/navigator/test_govern.py`. Lives: code src/startd8/navigator/govern.py. Approve?: does the verify obligation fire only for realized llm-regime targets with an empty verify?. Verify: an `llm`-regime edge to a lives-populated node with an empty `verify` yields a named invariant-9 finding; the same node with empty lives yields none; a `deterministic`-regime node with an empty `verify` yields none. Serves: O-2
- **FR-6 — realization as a derived §3a facet.** A node's realization facet — `realization:deterministic|llm|human|unknown`, and `realization:mixed` for a parent spanning regimes — is DERIVED from its incoming edges and exposed to the existing facet engine, so cross-cutting by realization works. Name: The node exposes a derived realization facet including mixed for non-uniform parents to the existing facet engine. Touches: `src/startd8/navigator/realization.py`, `tests/unit/navigator/test_realization.py`. Lives: code src/startd8/navigator/realization.py. Approve?: is realization a derived facet usable in the existing facet mechanism?. Verify: faceting a graph by `realization:llm` returns the llm-realized nodes, and a parent spanning regimes exposes `realization:mixed`. Serves: O-1
- **FR-7 — Additive, byte-identical, no construction coupling.** The whole feature is additive: existing domain renders (requirements/capability) are byte-identical (the determinism-% line renders only when regime data is present; the shipped fixtures carry none), the seam is unwired, and nothing imports a construction subsystem. Name: The realization feature is additive byte-identical and imports no construction subsystem. Touches: `tests/unit/wireframe/test_render_profile.py`, `tests/unit/navigator/test_realization.py`. Lives: test tests/unit/wireframe/test_render_profile.py. Approve?: are existing renders byte-identical and free of construction-subsystem imports?. Verify: `test_no_profile_is_byte_identical` passes unedited; a fixture with no declared regime renders no determinism-% line; `realization.py` imports nothing from `backend_codegen`/`contractors`/`micro_prime`. Serves: O-3

## Non-requirements

- **NR-1:** Approach (a) ships a DECLARED regime + a determinism-% labeled `declared`. Grounding it in MEASURED construction provenance is **approach (b)** — the named, additive follow-on that fills the seam. Do NOT wire a construction provenance source here.
- **NR-2:** Does NOT touch `backend_codegen` / `contractors` / `micro_prime` — (a) is navigator-internal; (b) builds the emitter + normalizer + `Node.lives.ref` join. The seam is the firewall that keeps that coupling behind a stable contract.
- **NR-3:** Does NOT implement planned-vs-realized (OQ-1) — a single declared regime; the planned-vs-realized regression delta is (b)'s self-monitoring payoff (needs measured regime + router data).
- **NR-4:** Does NOT add a general facet framework — realization is one derived facet on the existing §3a mechanism (anti-over-abstraction; the schema's "simplification not accretion" bar).
- **NR-5:** Build-blocked (not spec-blocked) on REQ-16/17 landing on `main` — the `regime` slot + edges live on `feature/req-16-17-node-schema-bump` (`aaa39178`), unmerged. This REQ is ready for the loop once that lands.
