# Measured Realization via a Provenance Contract (approach (b)) — Requirements

**Project:** startd8-sdk   **Criticality:** high
**Version:** 0.1   **Date:** 2026-08-16
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** *(plan deferred — spec-only; delivered via the Spec Delivery Loop)* · **`REQ-18` (approach (a) — the seam this fills)** · `RESEARCH_llm-interpreter-backend-and-realization-facet.md` (OQ-1..6) · `REQ-16` (the `regime` slot) · `REQ-17` (the `verify` field)
**Inherits standards:** det-req-kit · NODE-SCHEMA v0.4.0 · NAMING_CONVENTION · REQ-06 (govern) · REQ-18 (the confidence-aware seam) · `ContextCore/docs/design/DELIVERY_EVIDENCE_CONTRACT.md` (the contract-as-firewall pattern)
**Audience:** operator / SDK contributors / construction-pipeline owners (backend_codegen · contractors · micro_prime)
**Trust boundary:** local repo, read-only over generated artifacts; no network; **navigator reads ONLY the provenance contract, never construction internals**
**Data classification:** internal

> **Readable handle:** `feature/sdk-navigator-grounds-each-node-s-realization-3ad65e54`
> **Semantic name:** *SDK navigator grounds each node's realization regime in measured construction provenance via a stable provenance contract the deterministic and LLM generation paths emit, normalized into a per-file regime map joined to Node lives refs with a confidence score, so the determinism-% becomes measured not declared while a weak join honestly degrades, and surfaces planned-versus-realized regressions as named findings.*
> **Canonical ref:** `cc:intent:requirements-visualization:feature:req-19`

## 0. Why this exists — make the determinism-% true, without ever lying

REQ-18 shipped a *declared* determinism-% through a confidence-aware seam. This REQ (approach (b)) fills
that seam with **measured** regime, grounded in what the construction pipeline actually did — bringing the
one remaining asserted facet up to the IR's grounding standard (invariant 4), and unlocking the
**self-monitoring** the whole exercise was for: a node *planned* deterministic but *realized* by LLM is a
determinism regression, and that regression is currently invisible.

The load-bearing constraint is the same one that made (a) worth staging: **grounding a number wrongly is
worse than declaring it.** So (b) is built around two firewalls — (1) a **stable provenance *contract*** so
the navigator depends on a typed interface and never on construction internals (the modularity firewall,
the `DELIVERY_EVIDENCE_CONTRACT` pattern), and (2) REQ-18's **confidence-aware seam** so a weak file↔node
join **degrades to declared/`unknown`, never asserts a measurement** (the honesty firewall). (b) is
additive over (a): (a)'s declared path is the permanent fallback.

## Design decision — the contract is the coupling surface, and the only one

The navigator (a legibility layer) must not import `backend_codegen` / `contractors` / `micro_prime`. All
coupling goes through **one typed contract** (FR-1): the construction paths *emit* it, the navigator
*consumes* it. A construction subsystem may refactor freely as long as it still emits the contract; a
contract change is the sole reviewed coupling event (guarded by a contract test). This is what keeps (b)'s
cross-subsystem reach from becoming accidental entanglement.

## Overview

Define a typed **realization-provenance contract** (`{file, regime, source_confidence, provenance{model?,
strategy?, cost?}}`); have the deterministic (`backend_codegen` + `$0`-skip) and LLM (`contractors`/
`micro_prime`) paths **emit** it; **normalize** the ≥4 existing scattered sources into one per-file regime
map; **join** it to `Node.lives.ref` by file path with a **join confidence**; feed the measured regime into
REQ-18's seam so high-confidence matches relabel the determinism-% `measured` and weak matches degrade;
and surface **planned-vs-realized** regressions (router plan vs measured) as named `govern` findings. No new
Node field; (a)'s declared path is the fallback; the navigator imports only the contract.

## Objectives

- **O-1:** The determinism-% is MEASURED, grounded through the contract firewall — target: a high-confidence graph renders the determinism-% labeled `measured`, sourced from emitted construction provenance.
- **O-2:** The grounding is HONEST — target: a weak/absent join degrades to declared/`unknown` via REQ-18's seam and never asserts a `measured` value it cannot ground.
- **O-3:** Self-monitoring — target: a node planned deterministic but measured `llm` surfaces as a named determinism-regression finding.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| quality | A wrong file↔node join asserts a confidently-wrong regime (false grounding — worse than declared) | FR-4/FR-5: the join is confidence-scored and feeds REQ-18's seam, which degrades below threshold; a low-confidence match NEVER becomes `measured` | high |
| modularity | The navigator becomes coupled to construction internals | FR-1/NR-3: one typed contract is the sole coupling surface; the navigator imports only it; a contract test guards drift | high |
| quality | The ≥4 scattered sources conflict on a file's regime | FR-3: the normalizer resolves conflicts deterministically and records the resolution + a source_confidence | medium |
| scope | Acting on regressions (re-routing / contract enrichment), or a general provenance framework | NR-1/NR-4: FR-6 SURFACES the signal only; one contract for realization regime, not a framework | medium |
| dependency | REQ-18's seam must exist to fill | NR-6: spec-ready; build-blocked until REQ-18 lands on `main` |  high |

## Functional requirements

- **FR-1 — The realization-provenance contract (the modularity firewall).** Define a typed contract record `{file, regime (deterministic|llm|human), source_confidence, provenance{model?, strategy?, cost?}}` that construction paths emit and the navigator consumes, such that the navigator depends only on this contract and never on a construction subsystem's internals. Name: A typed realization-provenance contract is the sole coupling surface between construction and the navigator. Touches: `src/startd8/navigator/realization_contract.py`, `tests/unit/navigator/test_realization_contract.py`. Lives: code src/startd8/navigator/realization_contract.py. Approve?: is the provenance contract the only coupling surface the navigator depends on?. Verify: the contract is a typed schema; a malformed record is rejected with a named error; the navigator's realization path imports the contract module and no construction subsystem. Serves: O-1
- **FR-2 — The generation paths emit the contract.** The deterministic path (`backend_codegen` + the `$0`-skip hook) emits `regime=deterministic` records for the files it owns, and the LLM path (`contractors`/`micro_prime`) emits `regime=llm` records with `provenance.model`/`strategy`, both conforming to FR-1. Name: The deterministic and LLM generation paths emit conforming realization-provenance records per artifact. Touches: `src/startd8/backend_codegen/`, `src/startd8/contractors/`, `src/startd8/micro_prime/`, tests. Lives: code src/startd8/backend_codegen/assembler.py. Approve?: do both generation paths emit conforming per-artifact regime records?. Verify: a deterministic generation run emits `deterministic`-regime records for its owned files; an LLM generation run emits `llm`-regime records carrying `provenance.model`. Serves: O-1
- **FR-3 — Normalize the scattered sources into one per-file regime map.** A normalizer reads the existing provenance sources (`micro_prime` registry model/strategy, `prime-result`, the `$0`-skip decisions, generation-manifest) into a single per-file regime map, each record carrying a `source_confidence`, resolving conflicts deterministically. Name: A normalizer unifies the scattered generation-provenance sources into one per-file regime map with a source confidence. Touches: `src/startd8/navigator/realization_provenance.py`, tests. Lives: code src/startd8/navigator/realization_provenance.py. Approve?: does the normalizer produce one confidence-scored regime record per generated file?. Verify: the normalizer yields one record per generated file with a regime + `source_confidence`; two sources disagreeing on a file resolve to a single deterministic result with a recorded rationale. Serves: O-1
- **FR-4 — Confidence-scored join to Node lives refs.** Join the per-file regime map to each Node's lives refs by file path, producing a per-node measured regime plus a **join confidence**; a file matching no Node, and a Node whose lives match no file, are handled without crashing (they contribute no measured regime). Name: The per-file regime map joins to Node lives refs by path producing a per-node measured regime with a join confidence. Touches: `src/startd8/navigator/realization.py`, tests. Lives: code src/startd8/navigator/realization.py. Approve?: does the join produce a per-node measured regime with a confidence and handle non-matches safely?. Verify: a Node whose lives ref matches a deterministic file yields measured regime `deterministic` with high confidence; a Node whose lives match no file yields no measured regime (no crash). Serves: O-1, O-2
- **FR-5 — Fill the seam + relabel, honestly.** Feed the measured regime and its join confidence into REQ-18's confidence-aware seam: above the confidence threshold the measured regime wins and the summary determinism-% relabels `measured`; below it, the seam degrades to the declared regime (or `unknown`) and the label stays `declared` — a low-confidence match never becomes `measured`. Name: The measured regime fills the REQ-18 seam relabeling the determinism-% measured only above the confidence threshold else degrading. Touches: `src/startd8/navigator/realization.py`, `src/startd8/wireframe_view/compose.py`, tests. Lives: code src/startd8/navigator/realization.py. Approve?: does a high-confidence measure relabel to measured while a low-confidence one degrades to declared?. Verify: a high-confidence measured graph renders the determinism-% labeled `measured`; a stubbed low-confidence match degrades to declared/`unknown` and the label stays `declared`. Serves: O-2
- **FR-6 — Planned-vs-realized self-monitoring (OQ-1).** Surface the delta between the router's *planned* regime (from `classify_tier` + the `$0`-skip decision) and the *measured* realized regime as a named `govern` finding — a node planned `deterministic` but measured `llm` is a determinism regression — bounded to SURFACING the signal, not remediating it. Name: A govern finding surfaces each node where the planned regime and the measured realized regime disagree as a determinism regression. Touches: `src/startd8/navigator/govern.py`, `src/startd8/complexity/`, tests. Lives: code src/startd8/navigator/govern.py. Approve?: does a planned-deterministic but measured-llm node surface as a named regression finding?. Verify: a node planned `deterministic` but measured `llm` yields a named determinism-regression finding; a node whose plan and measurement agree yields none. Serves: O-3
- **FR-7 — Contract-firewalled, additive, byte-identical fallback.** The navigator's realization path imports only the FR-1 contract (never a construction subsystem); a contract-schema drift fails a contract test; and with no provenance present the render is byte-identical to REQ-18's declared path (the permanent fallback). Name: The navigator imports only the provenance contract and renders byte-identical to the declared fallback when provenance is absent. Touches: `tests/unit/navigator/test_realization_contract.py`, `tests/unit/wireframe/test_render_profile.py`. Lives: test tests/unit/navigator/test_realization_contract.py. Approve?: is the contract the only import and the no-provenance render byte-identical to (a)?. Verify: `realization.py`/`realization_provenance.py` import only `realization_contract`, not `backend_codegen`/`contractors`/`micro_prime`; a contract-schema change fails the contract test; a no-provenance render equals REQ-18's declared render. Serves: O-2

## Non-requirements

- **NR-1:** Does NOT remediate regressions (re-route, enrich the contract, re-run) — FR-6 surfaces the signal; acting on it is downstream (the RETROSPECTIVE bookend and the router's own tuning).
- **NR-2:** Does NOT change REQ-18's seam contract or the declared-regime fallback — (b) FILLS the seam and REUSES its honest-degradation; it never replaces it.
- **NR-3:** Does NOT couple the navigator to construction internals — ALL coupling is via the FR-1 contract; a construction subsystem's internal refactor must not break the navigator so long as it still emits the contract.
- **NR-4:** Does NOT build a general provenance framework — one contract + one join for realization regime (anti-over-abstraction; the schema's "simplification not accretion" bar).
- **NR-5:** Temporal binding uses the latest (or an explicitly named) construction run's provenance; multi-run history/archival is out of scope.
- **NR-6:** Build-blocked (not spec-blocked) on REQ-18 landing on `main` — (b) fills the seam (a) builds. Spec-ready now.
