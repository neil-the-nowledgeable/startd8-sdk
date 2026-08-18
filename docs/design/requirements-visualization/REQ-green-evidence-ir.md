# The GREEN-evidence IR — SARIF's missing complement, a first-class representation of what's PROVEN with liveness provenance — Requirements

**Project:** startd8-sdk   **Criticality:** high
**Version:** 0.1   **Date:** 2026-08-18
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** *(plan deferred — spec-only; delivered via the Spec Delivery Loop)* · **`RESEARCH_implicature-audit-and-the-missing-half-irs.md` (the definition + the D5 lattice + the §E resolution — the authority)** · `REQ-22` (verify-liveness — the per-node liveness this generalizes to corpus scale) · `REQ-23`/`REQ-25` (the fact-first + hypothesis liveness cells this lifts) · `REQ-18`/`REQ-19` (realization-provenance + the confidence-aware seam — a green-evidence instance) · `REQ-16` (the derivation edge that reconciles RED↔GREEN) · `REQ-20` (the retrospective destination) · `docs/design/deterministic-generation/ARCHITECTURE_sarif-determinism-ratchet.md` + `REQ-determinism-gap-census.md` (the codegen consumer — determinism-% IS green evidence)
**Inherits standards:** det-req-kit · NODE-SCHEMA v0.4.0 · NAMING_CONVENTION · REQ-06 (govern + FR-7 precision) · REQ-07 (advisory — the Validation Cockpit) · Harbor Honesty-Verdict (absence-vs-error) · `findings_sarif.py` duck-typed finding shape (the RED sink this mirrors) · honest-grounding (a green is cruft until grounded in a live proof)
**Audience:** operator / validator / SDK contributors / det-req-kit owners (cross-repo) / determinism strategist
**Trust boundary:** local; reads existing evidence artifacts (`lives[]`, `verify.gate` results, realization provenance, liveness cells); advisory (attestation/gap), never a blocking build gate; a dead green routes to a human-gated retrospective, never a silent pass
**Data classification:** internal

> **Readable handle:** `feature/green-evidence-ir-6be73464`
> **Semantic name:** *SDK navigator lifts the four scattered green-evidence seeds — lives evidence, verify-liveness gate results, realization-provenance regime-and-confidence, and the fact-first and hypothesis liveness cells — into one GREEN-evidence attestation IR that stands to proven as SARIF stands to wrong, each attestation carrying a claim-ref proof-kind liveness-provenance and confidence as the positive dual of a SARIF result, joined to the RED findings-half at the shared derivation edge not merged nor forked, consumed by the determinism-percent scoreboard as an instance of green evidence, placed at the retrospective bookend, all a lift not a new engine and additive advisory and byte-identical.*
> **Canonical ref:** `cc:intent:requirements-visualization:feature:green-evidence-ir`

## 0. Why this exists — SARIF carries only RED; the GREEN complement has no IR

The NLPS runs a findings-half IR — **SARIF** (`coverage_map/findings_sarif.py`) — that makes *what's WRONG /
missing / violated* first-class and censusable, the RED pole that fuels both metabolization loops. Its
complement — *what's PROVEN, and provably still live* — has **no first-class representation.** Today "proven"
is scattered across four seeds that never join: a `lives[]` evidence entry (where a claim is grounded), a
`verify.gate` liveness result (REQ-22 — a claim whose check is provably live), a realization-provenance stamp
(REQ-18/19 — the measured regime + its confidence), and the fact-first / hypothesis liveness cells
(REQ-23/25). None is a *unified, liveness-carrying evidence IR* the way SARIF is a unified findings IR.

This is the **D5 lattice gap** the research note names (`RESEARCH_implicature-audit-and-the-missing-half-irs.md`
§3.2/§3.6): the biggest *structural* half-IR gap in the NLPS. It is the **verify-liveness lacuna generalized
from per-node (REQ-22) to corpus scale** — the reason a requirement *can* read green while its guarantee is
dead is that no evidence-IR binds a green to a live gate with provenance. This REQ closes that at corpus scale:
a GREEN-evidence IR where every green carries `{claim-ref, proof-kind, liveness-provenance, confidence}`, so a
dead green is **never a silent pass** but a findable, censusable, degrade-to-human record. It is
`honest-grounding` applied to the pipeline's own greens — *a green is cruft until grounded in a live proof.*

**This is a LIFT of four existing seeds into one IR — NOT new machinery** (research §4.2: "lift these into one
IR, don't rebuild them"). The IR mirrors SARIF's *shape* (a duck-typed record stream, one renderer) at the
opposite polarity (attestation, not refutation), and reconciles with SARIF **at the derivation edge** — two
poles, one lattice, joined not merged (§E resolution).

## Design decisions

- **Mirror SARIF's shape, invert its polarity.** The GREEN-evidence attestation is the *positive dual* of a
  SARIF result: where a SARIF result carries `{rule-id, level, message, file, line}` refuting a claim, an
  attestation carries `{claim-ref, proof-kind, liveness-provenance, confidence}` confirming one. It is
  duck-typed and rendered by one function, exactly as `render_sarif_from_findings` duck-types every RED producer.
- **Lift, don't build (research §4.1).** The four seeds already exist and are typed — `NodeEvidence` (`lives[]`),
  `verify.gate` + `verify_oracle` liveness verdicts (REQ-22), `MeasuredProvenanceSource`/`node_regime`
  (REQ-18/19), the REQ-23/25 liveness cells. This REQ *reads* them into one attestation stream; it authors no
  new evidence and no new execution engine.
- **RED↔GREEN reconcile at the derivation edge, NOT by merge (§3.5 resolution).** SARIF and this IR answer
  opposite questions (what's wrong vs what's proven), carry opposite polarity, and have different consumers.
  They share the node grammar and are joined by the REQ-16 derivation edge (an attestation is *about* a Node;
  a SARIF finding is *about* the same Node). They are NOT merged into one IR and NOT forked into two grammars.
- **A determinism-% number IS green evidence (the codegen consumer).** `realization.py::determinism_pct` /
  `corpus_realization` measure *what's PROVEN deterministic, grounded through a confidence-aware seam* — an
  instance of a green-evidence attestation (proof-kind `realization`, its `grounded` flag = liveness-provenance,
  its `source_confidence` = confidence). This IR gives that number a home, not a parallel calculator.
- **Placed at the RETROSPECTIVE bookend (research §4.2).** The IR feeds the RETROSPECTIVE half of the two human
  bookends: it makes the actuals *attest*, so a `revises` that retires an invariant is gated on a *live* green,
  not a stale one. It is the linker's proof that every symbol resolves to something that actually runs.
- **Absence-vs-error (Harbor Honesty-Verdict).** An *absent* proof (a claim with no evidence at all) is
  distinguished from a *dead* proof (evidence present but its gate no longer attests), which is distinguished
  from a *live* proof — an absent green is never scored as a confirmed one (the `FIELDSTATE` guard).
- **Advisory, never blocking.** A dead/absent attestation routes to a human-gated retrospective decision
  (REQ-20 Lesson); it never halts a build. The shipped renders + app-scaffold path stay byte-identical.

## Overview

Define a **GREEN-evidence attestation record** — the positive dual of a SARIF result — carrying
`{claim-ref, proof-kind, liveness-provenance, confidence}`; **lift it from the four existing seeds** (`lives[]`
evidence, `verify.gate` liveness verdicts, realization-provenance, the REQ-23/25 liveness cells — reuse, cite
each, author nothing new); render an attestation stream through **one duck-typed renderer mirroring
`findings_sarif`**; join it to the RED findings-half **at the REQ-16 derivation edge** (peer IR, shared node
grammar, reconciled-not-merged — the §E resolution); expose the **determinism-% number as a green-evidence
instance** (the codegen consumer); place it at the **RETROSPECTIVE bookend** so a dead green routes to a
human-gated revision; honor **absence-vs-error** (absent ≠ dead ≠ live). Additive, advisory, reuse-only,
byte-identical.

## Objectives

- **O-1:** Proofs are first-class and censusable — target: a corpus's greens render as a GREEN-evidence attestation stream (one duck-typed renderer), each attestation carrying claim-ref + proof-kind + liveness-provenance + confidence, the positive dual of a SARIF result.
- **O-2:** The IR is a lift of the four seeds, not new machinery — target: every attestation derives from an existing seed (`lives[]`, `verify.gate`, realization-provenance, or a REQ-23/25 cell) with the seed cited; no new evidence-authoring or execution engine is introduced; determinism-% is exposed as a green-evidence instance.
- **O-3:** RED↔GREEN reconcile honestly and route to humans — target: a GREEN attestation and its RED counterpart join at the derivation edge (not merged); a dead/absent green is distinct from a live one and routes to a human-gated retrospective; the surfaces are advisory and byte-identical.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| scope | Building a new evidence/proof engine instead of lifting the four seeds | NR-1/FR-2..5: each attestation is *read from* an existing typed seed (cited); no new evidence-authoring, no new execution — a lift | high |
| integrity | Merging SARIF and the GREEN IR into one representation (the §E factorization failure) | NR-2/FR-6: two poles, one lattice, joined at the REQ-16 derivation edge — a peer IR, never a merged/forked one | high |
| quality | An *absent* proof (no evidence) read as a *confirmed* green — the `FIELDSTATE` bug at green polarity | FR-7: absence-vs-error — `absent` (no evidence) vs `dead` (evidence, gate no longer attests) vs `live` are three distinct verdicts; absent is never a confirmed green | high |
| scope | Re-deriving the determinism-% instead of exposing it as green evidence | FR-8: the determinism-% number IS a green-evidence attestation (proof-kind `realization`); reuse `realization.determinism_pct`/`corpus_realization`, no parallel calculator | high |
| security/integrity | Auto-retiring an invariant on a stale/dead green | FR-9/NR-3: a dead-green attestation PROPOSES a REQ-20 Lesson; a human applies — propose-don't-dispose; retiring is human-gated | high |
| quality | The attestation stream blocks the build / cries wolf | NR-4: advisory (attestation/gap), never blocking; byte-identical to clean corpora | medium |

## Functional requirements

- **FR-1 — The GREEN-evidence attestation record (the positive dual of a SARIF result).** Define a plain attestation record carrying `claim-ref` (the Node/FR the proof is about), `proof-kind` (`lives` | `verify-gate` | `realization` | `liveness-cell`), `liveness-provenance` (the live-verdict + when/how it last attested), and `confidence` — the confirming dual of a refuting SARIF result, a plain record not a framework. Name: A GREEN-evidence attestation carries claim-ref proof-kind liveness-provenance and confidence as the positive dual of a SARIF result. Touches: `src/startd8/navigator/green_evidence.py`, `src/startd8/coverage_map/findings_sarif.py`, tests. Lives: code src/startd8/navigator/green_evidence.py. Approve?: is the attestation a plain record with claim-ref proof-kind liveness-provenance and confidence and no dispatch framework?. Verify: an attestation instance carries the four fields and mirrors the SARIF result shape at inverted polarity; it is a plain record with no enum/dispatch engine and no new evidence authored. Serves: O-1
- **FR-2 — Lift from `lives[]` evidence (seed 1, reuse `NodeEvidence`).** An attestation of proof-kind `lives` is lifted directly from a Node's existing `lives[]` `NodeEvidence` entries — where the claim is grounded — reusing `default_confidence(lives)` for the confidence field; no new evidence is authored, the `lives[]` typed refs are read as-is. Name: A lives-kind attestation lifts a Node's existing lives evidence reusing default_confidence and authors no new evidence. Touches: `src/startd8/navigator/green_evidence.py`, `src/startd8/navigator/models.py`, tests. Lives: code src/startd8/navigator/green_evidence.py. Approve?: does a lives-kind attestation read the Node's existing lives refs and reuse default_confidence?. Verify: a Node with `lives[]` entries yields a `lives`-kind attestation whose confidence equals `default_confidence(node.lives)` and whose claim-ref is the node; a node with no lives yields no `lives`-kind attestation (absent, not a false green). Serves: O-2
- **FR-3 — Lift from verify-liveness gate results (seed 2, reuse REQ-22 `verify.gate`/`verify_oracle`).** An attestation of proof-kind `verify-gate` is lifted from a Node's `verify.gate` and its `verify_oracle` liveness verdict — a claim whose check is provably LIVE — with the verdict (`live` | `unrunnable` | `fail`) carried as liveness-provenance; a present-but-dead gate yields a `dead` attestation, never a confirmed green. Name: A verify-gate attestation lifts the REQ-22 gate liveness verdict so a present-but-dead gate is dead not a confirmed green. Touches: `src/startd8/navigator/green_evidence.py`, `src/startd8/navigator/verify_oracle.py`, tests. Lives: code src/startd8/navigator/green_evidence.py. Approve?: does a verify-gate attestation carry the REQ-22 liveness verdict distinguishing a live gate from a present-but-dead one?. Verify: a node whose `verify.gate` resolves and runs yields a `live` verify-gate attestation; a node whose gate is present but does not resolve/run yields a `dead` attestation via the REQ-22 verify-liveness verdict, not a confirmed green; the check reuses `verify_oracle` (no new execution engine). Serves: O-2
- **FR-4 — Lift from realization-provenance (seed 3, reuse REQ-18/19 seam).** An attestation of proof-kind `realization` is lifted from a Node's measured realization regime through the confidence-aware seam — the proven regime with its `source_confidence` as the attestation's confidence and the `grounded` flag as its liveness-provenance — reusing `node_regime`/`MeasuredProvenanceSource`; a below-threshold or absent measurement degrades to no attestation (never asserts what it cannot ground). Name: A realization-kind attestation lifts the measured regime and confidence through the REQ-18-19 seam degrading when it cannot ground. Touches: `src/startd8/navigator/green_evidence.py`, `src/startd8/navigator/realization.py`, tests. Lives: code src/startd8/navigator/green_evidence.py. Approve?: does a realization-kind attestation carry the measured regime and source_confidence through the REQ-18-19 seam and degrade below threshold?. Verify: a node with an above-threshold measured regime yields a `realization`-kind attestation carrying that regime and its `source_confidence`; a below-threshold or unmeasured node yields no `realization` attestation (degrades, never a false green); the confidence firewall (`CONFIDENCE_THRESHOLD`) governs. Serves: O-2
- **FR-5 — Lift from the REQ-23/25 liveness cells (seed 4, reuse the fact-first + hypothesis cells).** An attestation of proof-kind `liveness-cell` is lifted from the REQ-23 fact-first and REQ-25 hypothesis liveness cells — a target-set-measured or served-by-a-live-FR proof (fact-first) versus a precision-governed candidate (hypothesis) — carrying the cell's fact/candidate discipline into the attestation's liveness-provenance; the cells are read, not re-computed. Name: A liveness-cell attestation lifts the REQ-23 fact-first and REQ-25 hypothesis cells carrying their fact-versus-candidate discipline. Touches: `src/startd8/navigator/green_evidence.py`, `src/startd8/navigator/govern.py`, tests. Lives: code src/startd8/navigator/green_evidence.py. Approve?: does a liveness-cell attestation read the REQ-23 fact-first and REQ-25 hypothesis cells preserving fact-versus-candidate?. Verify: a REQ-23 fact-first live cell yields a fact-grounded `liveness-cell` attestation; a REQ-25 hypothesis cell yields a precision-governed candidate attestation; the two carry distinct liveness-provenance and the cells are read, not recomputed. Serves: O-2
- **FR-6 — RED↔GREEN reconcile at the derivation edge (the §E resolution, NOT a merge).** The GREEN attestation stream and the RED SARIF findings stream are peer IRs in one lattice, joined at the REQ-16 derivation edge — an attestation and a finding about the SAME Node are correlated by the shared node grammar and the edge, NOT merged into one representation and NOT forked into two grammars. Name: The GREEN attestation and the RED SARIF finding are peer IRs joined at the derivation edge not merged nor forked. Touches: `src/startd8/navigator/green_evidence.py`, `src/startd8/coverage_map/findings_sarif.py`, tests. Lives: code src/startd8/navigator/green_evidence.py. Approve?: are GREEN and RED joined at the derivation edge as peer IRs rather than merged into one representation?. Verify: a Node carrying both a GREEN attestation and a RED SARIF finding correlates them by the shared node key / derivation edge; no code path merges the two streams into a single record type, and each retains its own renderer. Serves: O-3
- **FR-7 — Absence-vs-error: absent ≠ dead ≠ live (the FIELDSTATE guard at green polarity).** An attestation distinguishes an *absent* proof (a claim with no evidence at all), a *dead* proof (evidence present but its gate no longer attests — the present-but-dead signature), and a *live* proof, so an absent green is never scored as a confirmed one — reusing the Harbor Honesty-Verdict absence-vs-error move. Name: An attestation distinguishes an absent proof from a dead proof from a live proof so absent is never a confirmed green. Touches: `src/startd8/navigator/green_evidence.py`, `src/startd8/navigator/govern.py`, tests. Lives: code src/startd8/navigator/green_evidence.py. Approve?: does an attestation separate absent from dead from live so an absent proof is never a confirmed green?. Verify: a claim with no evidence renders `absent`; a claim with present-but-dead evidence renders `dead`; a claim with a live gate renders `live`; the three carry distinct verdicts and an absent proof is never scored as a confirmed green. Serves: O-3
- **FR-8 — The determinism-% number IS green evidence (the codegen consumer).** The `realization.py::determinism_pct`/`corpus_realization` headline number is exposed as a green-evidence attestation of proof-kind `realization` (its `grounded` flag = liveness-provenance, its measured fraction = the proven-deterministic proof), so the codegen determinism ratchet's scoreboard reads through this IR rather than a parallel calculator — the determinism-gap census is a GREEN-evidence consumer. Name: The determinism-percent number is exposed as a realization-kind green-evidence attestation reusing realization.py not a parallel calculator. Touches: `src/startd8/navigator/green_evidence.py`, `src/startd8/navigator/realization.py`, tests. Lives: code src/startd8/navigator/green_evidence.py. Approve?: is the determinism-% exposed as a green-evidence attestation reusing realization.py rather than re-derived?. Verify: a corpus's `corpus_realization` result surfaces as a `realization`-kind attestation carrying the measured determinism-% and its `grounded` flag; the number reuses `determinism_pct` (no bespoke % arithmetic); an ungrounded corpus reads `declared`, never a false measured green. Serves: O-1, O-2
- **FR-9 — A dead/absent green routes to a human-gated retrospective (RETROSPECTIVE bookend).** A `dead` or unexpectedly-`absent` attestation for a claim that reads verified produces a grounded REQ-20 retrospective `Lesson` deriving-from the attestation and proposing a `revises` to the requirement, requiring explicit human sign-off — placing the IR at the RETROSPECTIVE bookend so a stale green retires an invariant only under human gate, never a silent pass. Name: A dead or absent green produces a grounded lesson proposing a human-gated revision at the retrospective bookend. Touches: `src/startd8/navigator/sources_retrospective.py`, `src/startd8/navigator/green_evidence.py`, tests. Lives: code src/startd8/navigator/sources_retrospective.py. Approve?: does a dead or absent green become a human-gated retrospective proposal rather than a silent pass?. Verify: a `dead`/unexpected-`absent` attestation on a verified claim produces a `proposed` REQ-20 Lesson deriving-from the attestation and revising the requirement; retiring the invariant requires an explicit human accept; no path auto-applies. Serves: O-3
- **FR-10 — Lift, additive, advisory, byte-identical.** All of the above is a LIFT of the four seeds (no new evidence-authoring or execution engine — research §4.1), mirrors `findings_sarif`'s one-duck-typed-renderer shape (not a merge of it — NR-2), is advisory (attestation/gap, not blocking), and leaves the shipped renders + app-scaffold path byte-identical. Name: The GREEN-evidence IR is a lift of the four seeds additive advisory and byte-identical. Touches: `tests/unit/navigator/test_green_evidence.py`, `tests/unit/wireframe/test_render_profile.py`. Lives: test tests/unit/navigator/test_green_evidence.py. Approve?: is the IR a lift of existing seeds additive advisory and byte-identical?. Verify: the module imports the four existing seeds (no new evidence/execution engine); the attestation stream is advisory (non-blocking); `test_no_profile_is_byte_identical` passes unedited. Serves: O-1, O-3

## Non-requirements

- **NR-1:** Does NOT author new evidence or build a new proof/execution engine — it LIFTS the four existing typed seeds (`lives[]` `NodeEvidence`, `verify.gate`/`verify_oracle`, realization-provenance, REQ-23/25 cells) into one attestation stream (research §4.1: "lift these into one IR, don't rebuild them").
- **NR-2:** Does NOT merge SARIF and the GREEN IR into one representation, and does NOT fork them into two grammars — they are peer IRs in one lattice, joined at the REQ-16 derivation edge (the §E resolution: two poles, one lattice, reconciled by the edge, not by merger).
- **NR-3:** Does NOT auto-retire an invariant on a dead/stale green — a dead-green attestation PROPOSES a REQ-20 Lesson; a human applies (propose-don't-dispose).
- **NR-4:** Does NOT block the build — advisory (attestation/gap), consistent with the Validation Cockpit (REQ-07 NR-1); byte-identical to clean corpora.
- **NR-5:** Does NOT re-derive the determinism-% — reuses `realization.py::determinism_pct`/`corpus_realization` and its confidence-aware seam; the IR exposes the number as an attestation, it does not compute a parallel one.
- **NR-6:** Does NOT author end-user / company content (bucket 4) — the IR represents *proofs about the pipeline's own claims*; it does not generate the real value content the commissioning company provides.
- **NR-7:** The `proof-kind` set (`lives` | `verify-gate` | `realization` | `liveness-cell`) is a plain lifted enumeration of the four seeds, NOT an extensible dispatch framework (the over-abstraction guard — a new proof-kind is a data-only add of another lifted seed, never a new engine).
- **NR-8:** Build-blocked (not spec-blocked) on the four seeds: REQ-18/19 (realization + seam) and REQ-22 (verify-liveness) have landed; REQ-23/25 (liveness cells) and REQ-20 (the Lesson destination) are the remaining build dependencies. This is their lift.
