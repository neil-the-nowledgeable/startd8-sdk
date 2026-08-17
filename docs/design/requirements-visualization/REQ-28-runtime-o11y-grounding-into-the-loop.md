# Route Runtime Observability into the Loop (the territory edge) — Requirements

**Project:** startd8-sdk   **Criticality:** high
**Version:** 0.1   **Date:** 2026-08-17
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** *(plan deferred — spec-only; delivered via the Spec Delivery Loop)* · **`ANALYSIS_runtime-grounding-feature-and-ai-o11y.md`** · `CHARTER_det-doc-kit-family.md` (invariant 7) · `REQ-19` (the realization seam this fills) · `REQ-22/23` (the liveness layer this extends) · `REQ-20` (the retrospective destination)
**Inherits standards:** det-req-kit · NODE-SCHEMA v0.4.0 · NAMING_CONVENTION · REQ-06 (govern) · REQ-07 (advisory) · Harbor Honesty-Verdict (absence-vs-error) · the o11y→SARIF bridge (`c8fc0314`)
**Audience:** operator / validator / SDK contributors / SRE
**Trust boundary:** local; reads existing o11y artifacts; advisory (candidate/gap), never blocking; the generative fix proposes a patch, human applies
**Data classification:** internal

> **Readable handle:** `feature/sdk-navigator-routes-runtime-observability-8c3a4932`
> **Semantic name:** *SDK navigator routes runtime observability signals into the loop by surfacing a declared feature with no live emission as a runtime verify-liveness gap through the SARIF finding-bus, grounding each node's measured realization regime and its planned-versus-realized determinism regression in AI cost telemetry via the REQ-19 seam, and offering instrumentation-gen as the generative fix for an observability gap, all advisory and human-gated and reusing existing pieces.*
> **Canonical ref:** `cc:intent:requirements-visualization:feature:req-28`

## 0. Why this exists — close the circle in the territory

The loop grounds claims in the *map* (docs/code, authoring-time). The circle only closes when they are also
grounded in the *territory* (the running system). This REQ wires the two runtime signals — **feature o11y**
(`observability/parity.py` compare-live: does the deployed feature emit a live signal?) and **AI o11y**
(`costs/otel_metrics.py`: what did generation actually cost?) — into the SAME loop, reusing the already-routed
o11y→SARIF bridge and REQ-19's realization seam. It is **all reuse** (charter §7): no new engine, advisory only,
human-gated. The result: "verified" means *"the feature emits a live signal proving it works, and here's what it
cost to build."*

## Design decisions

- **Reuse, don't build.** `parity.py` (compare-live), `costs/otel_metrics.py` (AI cost), `instrumentation_gen.py`
  (the generative fix), `coverage_map/findings_sarif.py` (the SARIF renderer) and the routed o11y→SARIF bridge
  all exist; this REQ wires them into the loop.
- **Runtime is the deepest liveness altitude** — a feature-emission gap extends the liveness column above the
  static cells (REQ-22/23), through the same SARIF sink.
- **Absence-vs-error (Harbor Honesty-Verdict)** — an *absent* metric must be distinguished from a real `0` (the
  `FIELDSTATE` bug); a runtime finding classifies `unrunnable/absent` (provenance) vs `real-fail` (territory).
- **Advisory + human-gated** — a runtime gap routes to a human decision (a REQ-stub via `sarif_to_req_stub` or a
  generated instrumentation patch via `instrumentation_gen`); it never blocks and never auto-applies.

## Overview

Surface a declared feature with no live emission (`parity.py` compare-live) as a **runtime-verify-liveness GAP**
in the liveness layer, emitted through the o11y→SARIF bridge; ground each node's **measured** realization regime
+ its planned-vs-realized determinism regression (REQ-19 FR-6) in **AI o11y cost telemetry** via REQ-19's seam;
offer `instrumentation_gen` as the `$0` generative fix for a feature-o11y gap (propose a patch, human applies);
and honor absence-vs-error. Additive, advisory, reuse-only; the shipped surfaces are byte-identical.

## Objectives

- **O-1:** A deployed feature with no live signal is a loud gap — target: `parity.py`'s dead-SLI class surfaces as a runtime-verify-liveness GAP through the SARIF sink; a feature that emits flags 0.
- **O-2:** The realization regime is grounded in live AI telemetry — target: a node's measured regime + a planned-`$0`-but-cost-observed determinism regression derive from `costs/otel_metrics` via the REQ-19 seam.
- **O-3:** Cheap, honest, human-gated — target: the fix reuses `instrumentation_gen`/`sarif_to_req_stub` (proposes, never auto-applies); absent vs real-0 are distinguished; advisory, byte-identical.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| quality | An *absent* metric read as a real `0` (the Harbor `FIELDSTATE` bug) | FR-4: absence-vs-error — a finding classifies `unrunnable/absent` distinctly from `real-fail` | high |
| scope | Building new o11y instead of wiring | NR-2: reuse `parity`/`costs`/`instrumentation_gen`/`findings_sarif` + the routed bridge | high |
| security/integrity | Auto-applying a generated instrumentation patch or a stub | FR-5/NR-1: the generative fix PROPOSES (a patch / a REQ-stub); a human applies — propose-don't-dispose | high |
| quality | The runtime check blocks the pipeline / cries wolf | NR-3: advisory (candidate/gap), never blocking | medium |
| dependency | Needs the realization seam + liveness layer + the o11y modules | NR-4: REQ-18/19 + REQ-22/23 built; `parity`/`costs`/`instrumentation_gen`/the bridge exist |  medium |

## Functional requirements

- **FR-1 — Runtime verify-liveness from compare-live.** Surface `observability/parity.py`'s declared-vs-emitted result (a declared feature/SLI with no live emission) as a runtime-verify-liveness GAP registered in the liveness layer and emitted through the o11y→SARIF bridge — the deepest cell of the liveness column. Name: A declared feature with no live emission surfaces as a runtime verify-liveness gap through the SARIF sink. Touches: `src/startd8/navigator/govern.py`, `src/startd8/observability/parity.py`, tests. Lives: code src/startd8/navigator/govern.py. Approve?: does a feature with no live signal render a runtime-verify-liveness GAP via parity and the SARIF sink?. Verify: a declared feature whose `parity` result shows no live emission yields a runtime-verify-liveness GAP routed through the SARIF sink; a feature that emits yields none. Serves: O-1
- **FR-2 — Measured realization from AI cost telemetry.** A node's measured realization regime derives from `costs/otel_metrics` AI-cost telemetry through REQ-19's confidence-aware seam — a node with observed LLM cost measures `llm`, one with none measures `deterministic` (subject to the seam's confidence degradation). Name: A node's measured realization regime derives from AI cost telemetry through the REQ-19 seam. Touches: `src/startd8/navigator/realization.py`, `src/startd8/costs/otel_metrics.py`, tests. Lives: code src/startd8/navigator/realization.py. Approve?: does AI cost telemetry ground the measured realization regime via the REQ-19 seam?. Verify: a node with observed LLM cost measures `llm` through the seam; a node with no observed cost degrades to declared/`unknown` (never a false `deterministic`); the seam's confidence gate governs. Serves: O-2
- **FR-3 — Planned-vs-realized regression, grounded.** A node planned `deterministic` (`$0`) whose AI o11y shows real LLM cost surfaces as a MEASURED determinism-regression finding (REQ-19 FR-6) through the SARIF sink — the regression is now grounded in live telemetry, not a static provenance file. Name: A planned-deterministic node with observed LLM cost surfaces as a measured determinism-regression finding. Touches: `src/startd8/navigator/govern.py`, `src/startd8/costs/otel_metrics.py`, tests. Lives: code src/startd8/navigator/govern.py. Approve?: does a planned-$0 node with observed cost surface a measured regression?. Verify: a node planned `deterministic` with observed LLM cost yields a named determinism-regression finding via the SARIF sink; agreement (planned matches measured) yields none. Serves: O-2
- **FR-4 — Absence-vs-error (the FIELDSTATE guard).** A runtime finding distinguishes an *absent* signal (the metric was never emitted — provenance) from a real failing value (the feature ran and reported bad — territory), so an absent field is never misread as a real `0` (the Harbor `FIELDSTATE_EXPLICIT_STATE` bug), reusing the Harbor Honesty-Verdict. Name: A runtime finding distinguishes an absent signal from a real failing value so absent is never misread as zero. Touches: `src/startd8/navigator/govern.py`, `src/startd8/observability/parity.py`, tests. Lives: code src/startd8/navigator/govern.py. Approve?: does the finding separate an absent signal from a real failing value?. Verify: an absent metric classifies `unrunnable/absent`; a metric present but failing classifies `real-fail`; the two carry distinct findings and an absent field is never scored as a real `0`. Serves: O-3
- **FR-5 — Generative fix: propose, don't dispose.** A feature-o11y gap offers a `$0` generative fix via `scaffold_codegen/instrumentation_gen` (generate the instrumentation patch that makes the feature emit) and/or a REQ-stub via `sarif_to_req_stub`; both are PROPOSED for human application — never auto-applied. Name: A feature-o11y gap proposes an instrumentation patch or a REQ-stub for human application never auto-applied. Touches: `src/startd8/navigator/govern.py`, `src/startd8/scaffold_codegen/instrumentation_gen.py`, tests. Lives: code src/startd8/navigator/govern.py. Approve?: does a feature-o11y gap propose (not auto-apply) an instrumentation patch or REQ-stub?. Verify: a feature-o11y gap yields a proposed `instrumentation_gen` patch (or a `sarif_to_req_stub` REQ-stub) requiring an explicit human apply; no code path applies the patch autonomously. Serves: O-3
- **FR-6 — Reuse, additive, advisory, byte-identical.** All of the above reuses `parity`/`costs`/`instrumentation_gen`/`findings_sarif` + the routed o11y→SARIF bridge (no new engine); the checks are advisory (candidate/gap, not blocking); and the shipped renders + app-scaffold path are byte-identical. Name: The runtime grounding reuses existing o11y pieces and is additive advisory and byte-identical. Touches: `tests/unit/navigator/test_runtime_grounding.py`, `tests/unit/wireframe/test_render_profile.py`. Lives: test tests/unit/navigator/test_runtime_grounding.py. Approve?: is the wiring reuse-only additive advisory and byte-identical?. Verify: the wiring imports the existing o11y modules (no new engine); the checks are advisory (non-blocking); `test_no_profile_is_byte_identical` passes unedited. Serves: O-1, O-3

## Non-requirements

- **NR-1:** Does NOT auto-apply a generated instrumentation patch or a REQ-stub — the generative fix PROPOSES; a human applies (propose-don't-dispose).
- **NR-2:** Does NOT build new observability — reuses `parity.py` (compare-live), `costs/otel_metrics.py`, `instrumentation_gen.py`, `findings_sarif.py`, and the routed o11y→SARIF bridge.
- **NR-3:** Does NOT block the build — advisory (candidate/gap); a runtime gap routes to a human decision.
- **NR-4:** Build-ready — REQ-18/19 (realization + seam) and REQ-22/23 (liveness layer) are built; the o11y modules and the SARIF bridge exist. This is their wiring.
- **NR-5:** Does NOT change the o11y modules' own contracts — it consumes their outputs (parity results, cost telemetry) and routes them; it does not re-author `parity`/`costs`.
