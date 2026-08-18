# Census the Determinism Gap — where the LLM is load-bearing per language (the deep-dive's first move) — Requirements

**Project:** startd8-sdk   **Criticality:** high
**Version:** 0.1   **Date:** 2026-08-18
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** *(plan deferred — spec-only; the "first move" of a deterministic-generation deep-dive)* · **`dev-os/CRP-INDEX.md`** (the doc-side recurring-themes twin this mirrors) · `REQ-18/19` (the realization seam this reuses for the determinism-% metric) · `docs/design/round3-full-app/BENCHMARK_METHODOLOGY.md` (the census corpus)
**Inherits standards:** det-req-kit · NAMING_CONVENTION · the shared `RuleCatalog(producer, rules→SARIF level)` registry (`rule_catalog_base.py`) · the universal SARIF renderer (`coverage_map/findings_sarif.py`) · Harbor Honesty-Verdict (absence-vs-error) · advisory-not-blocking (REQ-07 posture)
**Audience:** SDK contributors / determinism strategist / benchmark operator
**Trust boundary:** local; instruments the LLM-driven construction path in-place; advisory (census/report), never blocking; emits findings + a report, proposes nothing auto-applied
**Data classification:** internal

> **Readable handle:** `feature/sdk-determinism-gap-census-044ea2e6`
> **Semantic name:** *SDK determinism-gap census instruments the polyglot LLM-driven construction path to emit a SARIF finding per LLM-call and per repair-intervention tagged by finding-class × language × element-kind, derives a per-language determinism-% scoreboard from the realization seam, and produces a ranked where-the-LLM-is-load-bearing-per-language census report over the Round-3 fleet as the input to a metabolization ratchet, all additive advisory and reuse-only.*
> **Canonical ref:** `cc:intent:deterministic-generation:feature:determinism-gap-census`

## 0. Why this exists — measure the gap before closing it

StartD8 has **two generation paths**: (1) deterministic $0 codegen (`backend_codegen/` + sibling `*_codegen/`, **Python-only**,
a contract rendered → code as a pure function); (2) LLM-driven polyglot construction (Prime + `micro_prime/`, 5 languages).
The polyglot path leaks LLM cost **precisely where a deterministic RENDERER is missing**: `src/startd8/languages/` has per-language
PARSE (`*_parser.py`) + SPLICE (`*_splicer.py`) + verify (`*_semantic_checks.py`), but **no renderer** (confirmed — no `*render*`
module, no `def render` in the package). The LLM does render-work that is often **templatable, not reasoning**.

We cannot decide *which* render-templates to build by intuition. The **census is the code-side twin of `dev-os/CRP-INDEX.md`'s
recurring-themes table**: instrument the polyglot path to emit **a finding per LLM-call and per repair-intervention**, tagged by
**finding-class × language × element-kind**, so we learn *where the LLM is load-bearing per language* — an evidence base that tells
us which render-templates to build **before building any**. The output is the **input to a metabolization ratchet**: a recurring
finding-class (e.g. "Go struct constructors, every service") → a deterministic render-template → the gap shrinks, measurably.

## Design decisions

- **Measure, don't fix (this move).** This REQ builds the *census*, not the renderers. The census names the gaps and ranks them;
  building a render-template is a downstream metabolization move it *feeds*, deliberately out of scope here.
- **Reuse the SARIF finding-bus, don't build a new one.** New finding-classes register in `rule_catalog_base.RuleCatalog`
  (a **data-only add** — a 5th producer `startd8-census` alongside the four existing) and render through the universal
  `coverage_map/findings_sarif.render_sarif_from_findings` (duck-typed; no per-producer adapter). No new emitter.
- **Reuse the realization seam for the headline %.** The per-language determinism-% is derived from `navigator/realization.py`
  (REQ-18/19) — its confidence-aware provenance seam already measures the `deterministic|llm` regime per node. We feed it the
  census's per-file regime observations; we do not rebuild a % calculator.
- **A census finding is an OBSERVATION, not a defect.** An LLM-call on an element the LLM *had* to reason about is expected and
  fine; the census records it so the *aggregate* reveals which finding-classes recur enough to be worth a template. Severity is
  `info` by default (it is a measurement, not a fault) — a finding-class earns attention by **frequency × language spread**, not by level.
- **Absence-vs-error honesty (Harbor Honesty-Verdict).** A language with **zero** observed LLM-calls (the census never ran that lane)
  must be distinguished from a language **measured** at 100% deterministic (ran, no LLM needed). An un-instrumented lane is `absent`,
  never a false `0% LLM`.
- **The Round-3 fleet is the ready corpus.** The `benchmark_matrix/fleet/` Online Boutique (9 services across go/node/python/csharp)
  is a live, integrated, multi-language build already driven by the harness — the census runs over it with no new corpus to author.
- **Additive · advisory · reuse-only.** The instrumentation is a passive hook (records; never alters generation); the census is a
  report; nothing blocks the pipeline and no generated artifact changes byte-for-byte when the census is off.

## Overview

Add a passive **SARIF instrumentation hook** at every LLM-call boundary and every repair-intervention in the LLM-driven
construction path (`micro_prime/engine.py` per-language branches + repair pipeline; `contractors/` Prime draft/repair boundaries),
tagging each observation with **finding-class × language × element-kind**, registered as a new `RuleCatalog` producer and rendered
through the existing universal SARIF renderer. Derive a **per-language determinism-% scoreboard** by feeding the census's per-file
regime observations into `navigator/realization.py`'s seam. Aggregate the findings into a ranked **"where the LLM is load-bearing
per language" census report** — the code-side twin of `CRP-INDEX.md`'s recurring-themes table — run over the Round-3 fleet. Honor
absence-vs-error. Additive, advisory, reuse-only; generated artifacts are byte-identical when the census is off.

## Objectives

- **O-1:** Every LLM-call and repair-intervention in the polyglot path is a tagged, replayable observation — target: each boundary emits a census finding carrying `finding-class × language × element-kind` through the existing SARIF bus; the census-off path is byte-identical.
- **O-2:** The determinism gap is a per-language number, honestly grounded — target: a per-language determinism-% scoreboard derives from `realization.py`'s seam; an un-instrumented lane reads `absent`, never a false `0% LLM`.
- **O-3:** The census names WHICH render-templates to build first — target: a ranked report groups findings by finding-class × language, ranked by frequency × language-spread, framed as the metabolization ratchet's input (recurring finding-class → candidate deterministic template).
- **O-4:** The census runs over the real corpus for free — target: the census executes over the Round-3 fleet (go/node/python/csharp) with no new corpus authored, reusing the `benchmark_matrix/fleet/` harness.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| scope | Building the render-templates instead of measuring the gap (doing the ratchet's next move now) | NR-1: this REQ is the census only; a template is a downstream metabolization move it feeds | high |
| scope | Building a new SARIF emitter / finding-bus instead of reusing | NR-2/FR-1: register a `RuleCatalog` producer + render via `findings_sarif` (data-only add, no new emitter) | high |
| quality | An un-instrumented language read as "100% deterministic" (the FIELDSTATE absence-as-zero bug) | FR-4: absence-vs-error — a lane with zero observations is `absent`, distinct from a measured 100%-deterministic lane | high |
| quality | The hook alters generation (perturbs what it measures / changes bytes) | FR-6/NR-3: the hook is passive (records only); the census-off render path is byte-identical | high |
| dependency | Instrumentation points don't exist where assumed | NR-4: grounded — `micro_prime/engine.py` per-language branches + `repair/orchestrator.py` `_repair_single_*` + `contractors/` draft boundaries confirmed; the fleet corpus is live | medium |
| quality | Census cries wolf — treats every LLM-call as a defect | design-decision: a finding is an `info` OBSERVATION; attention is earned by frequency × spread, not level | medium |

## Functional requirements

- **FR-1 — SARIF instrumentation hook at every LLM-call and repair-intervention.** A passive hook at each LLM-call boundary and each repair-intervention in the LLM-driven construction path emits a census finding tagged with the finding-class, the language, and the element-kind, registered as a new `startd8-census` `RuleCatalog` producer and rendered through the existing universal SARIF renderer — a data-only add, no new emitter. Name: A passive hook emits a census SARIF finding at every LLM-call and repair-intervention tagged by finding-class language and element-kind. Touches: `src/startd8/census/hook.py`, `src/startd8/census/rule_catalog.py`, `src/startd8/micro_prime/engine.py`, `src/startd8/repair/orchestrator.py`, tests. Lives: code src/startd8/census/hook.py. Approve?: does each LLM-call and repair-intervention emit a census finding tagged by finding-class language and element-kind via the existing SARIF bus?. Verify: driving the polyglot path over a fixture emits one census finding per LLM-call and per repair-intervention, each carrying finding-class × language × element-kind and rendering through `render_sarif_from_findings` with producer `startd8-census`. Serves: O-1
- **FR-2 — Finding-classes registered in the shared rule catalog.** The census's finding-classes (the taxonomy of LLM-load reasons — e.g. `element-render`, `body-fill`, `signature-render`, `repair-syntax`, `repair-import`, `repair-contract`) are registered as a `RULE_CATALOG` on a single `RuleCatalog(producer="startd8-census", …)` instance, each with a default `info` severity and a domain, so a new finding-class is a data-only add that inherits the shared no-dot / qualified-id / help-uri validation. Name: The census finding-classes register as a data-only RuleCatalog producer inheriting the shared validation. Touches: `src/startd8/census/rule_catalog.py`, `pyproject.toml`, tests. Lives: code src/startd8/census/rule_catalog.py. Approve?: are the census finding-classes a data-only RuleCatalog add with the shared validation?. Verify: `census/rule_catalog.py` instantiates one `RuleCatalog(producer="startd8-census", ...)`; every finding-class resolves a `severity`/`domain`/`qualified_id`; adding a class requires no code change to `rule_catalog_base`. Serves: O-1
- **FR-3 — Per-language determinism-% scoreboard from the realization seam.** A per-language determinism-% scoreboard derives from `navigator/realization.py`'s confidence-aware seam by supplying the census's per-file regime observations (a file the LLM touched measures `llm`; one only rendered deterministically measures `deterministic`) as a `ProvenanceSource`, so the headline number reuses REQ-18/19's `determinism_pct` rather than a new calculator. Name: A per-language determinism-percent scoreboard derives from the realization seam fed by census regime observations. Touches: `src/startd8/census/scoreboard.py`, `src/startd8/navigator/realization.py`, tests. Lives: code src/startd8/census/scoreboard.py. Approve?: does the per-language determinism-% derive from realization.py's seam fed by census observations?. Verify: the scoreboard constructs a `ProvenanceSource` from census observations and computes each language's determinism-% via `realization.determinism_pct`; a lane with all-deterministic files reads 100%, one with LLM-touched files reads below 100%, and no bespoke % arithmetic is introduced. Serves: O-2
- **FR-4 — Absence-vs-error: an un-instrumented lane is absent, never a false zero.** The scoreboard distinguishes a language with zero census observations (the lane was never instrumented/run — `absent`) from a language measured at 100% deterministic (ran, no LLM needed), so an un-run lane is never rendered as a real `0% LLM` / `100% deterministic`, reusing the Harbor Honesty-Verdict absence-vs-error distinction. Name: The scoreboard renders an un-instrumented lane as absent distinct from a measured 100-percent-deterministic lane. Touches: `src/startd8/census/scoreboard.py`, tests. Lives: code src/startd8/census/scoreboard.py. Approve?: does a lane with zero observations render absent rather than a false 100-percent-deterministic?. Verify: a language with no census observations renders `absent` (no %); a language with observations all-deterministic renders a measured 100%; the two are distinct rows and an absent lane is never scored as a real determinism number. Serves: O-2
- **FR-5 — Ranked census report: where the LLM is load-bearing per language.** A census aggregator groups the findings by finding-class × language and produces a ranked report — the code-side twin of `CRP-INDEX.md`'s recurring-themes table — ordered by frequency × language-spread, each row framed as a metabolization-ratchet candidate (a recurring finding-class → a candidate deterministic render-template), plus the FR-3 scoreboard. Name: A census aggregator produces a ranked where-the-LLM-is-load-bearing report framed as metabolization-ratchet input. Touches: `src/startd8/census/report.py`, tests. Lives: code src/startd8/census/report.py. Approve?: does the aggregator rank finding-class × language by frequency × spread and frame each row as a ratchet candidate?. Verify: the report groups census findings by finding-class × language, ranks by frequency × language-spread, renders each top row as a candidate template (finding-class → render-template) and embeds the FR-3 scoreboard; an empty census yields an honest empty report. Serves: O-3
- **FR-6 — Run over the Round-3 fleet, additive/advisory/byte-identical.** The census runs over the `benchmark_matrix/fleet/` Round-3 Online Boutique corpus (go/node/python/csharp) via the existing harness with no new corpus authored; the instrumentation is passive (records only, never alters generation); the census is advisory (a report, never blocking); and the census-off render path is byte-identical. Name: The census runs over the Round-3 fleet additive advisory and byte-identical. Touches: `tests/unit/census/test_fleet_census.py`, `tests/unit/census/test_byte_identical.py`. Lives: test tests/unit/census/test_fleet_census.py. Approve?: does the census run over the Round-3 fleet passively advisory and byte-identical when off?. Verify: the census executes over the fleet corpus emitting a report across go/node/python/csharp; the hook is passive (a census-off run produces byte-identical generated artifacts, asserted by a golden test); no census path blocks the pipeline. Serves: O-3, O-4

## Non-requirements

- **NR-1:** Does NOT build the deterministic render-templates — this REQ is the census (the measurement); a render-template is the downstream metabolization move the census feeds. Naming candidates is in scope; building them is not.
- **NR-2:** Does NOT build a new SARIF emitter or finding-bus — reuses `rule_catalog_base.RuleCatalog` (a data-only producer add) and `coverage_map/findings_sarif.render_sarif_from_findings` (the universal duck-typed renderer).
- **NR-3:** Does NOT block the pipeline and does NOT alter generation — the hook is passive (records observations); the census is advisory; generated artifacts are byte-identical when the census is off.
- **NR-4:** Does NOT touch the deterministic $0 codegen path (`backend_codegen/` + siblings) — that path is already 100% deterministic by construction; the census instruments the LLM-driven path only, where the gap lives.
- **NR-5:** Does NOT author a new benchmark corpus — reuses the live `benchmark_matrix/fleet/` Round-3 fleet. Java (in the 5-language set but absent from the fleet) reads `absent` on the scoreboard until a Java corpus is instrumented (FR-4), never a false measurement.
- **NR-6:** Does NOT re-derive the determinism-% — reuses `navigator/realization.py`'s `determinism_pct` and its confidence-aware seam; the census contributes observations, not a parallel calculator.
