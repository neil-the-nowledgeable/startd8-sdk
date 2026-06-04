# Sapper — Pre-Execution Plan Validation — Implementation Plan

**Version:** 0.3 (IMPLEMENTED — Phases 0–6 landed on `feature/sapper-preexecution-validation`)
**Date:** 2026-06-04
**Status:** Implemented + tested. All 12 FRs realized in `src/startd8/sapper/` (11 modules, ~1.6k LOC) with
**41 passing unit tests** (`tests/unit/sapper/`), including the RUN-028 replay through the live toolchain.
Pairs with requirements v0.6.

**Implementation status (this branch):**

| FR | Module | Tests | Note |
|----|--------|-------|------|
| FR-SAP-1/2/3 | `models.py`, `extractor.py` | `test_models` (14) | schema, ranking, reason-enum, fingerprint |
| FR-SAP-4 | `pilot_bore.py` | `test_pilot_bore` (6) | overlay+toolchain, isolation, robustness; RUN-028 `Match` replay (mypy-gated) |
| FR-SAP-10 + OQ-6 | `convention_route.py` + `repair/convention.py` | `test_convention_route` (4) | SQLAlchemy import rule added; Flask/module-source on skeletons |
| FR-SAP-5/6 | `cross_contract.py`, `rules_sapper.py` | `test_cross_contract_and_rules` (7) | versioned-tolerant; fillability + reserved-name (override-tolerant) |
| FR-SAP-7 | `fde.py` | `test_fde` (5) | typed contract, ProjectKnowledge-backed, OMIT≠timeout, cache |
| FR-SAP-8/9/11/12 | `gate.py`, `report.py`, `host.py` | `test_gate_integration` (5) | ranked report, injection block, metrics, input_absent, gated-off blocking |

**Deferred (plan-scope, not blocking the vertical slice):**
- `startd8.preflight_rules` entry-point registration — the FR-SAP-6 checks are wired into the gate directly;
  the thin `PreflightRule` wrapper for prompt-enrichment is not yet registered in `pyproject.toml`.
- Deep wiring of `sapper_preflight_hook` into `domain_preflight_workflow.py` (+ loading EMIT artifacts from
  disk) — the host seam exists and is tested with in-memory inputs; the workflow call-site + EMIT loader remain.
- Real prompt injection at the `prime_contractor` / `micro_prime` call-sites (the injection *block* is built and
  tested; threading it into the prompt builders remains).
- OQ-1 MYPYPATH copy-free overlay; R2-F1 mypy-cache reuse; CLI flags (R4-F1/R5-F2). All optimizations/UX.

---

## 1. Module layout

New package `src/startd8/sapper/` (parallels `security_prime/`, `query_prime/` — orchestration over existing
machinery, not a new engine):

| File | FRs | Responsibility |
|------|-----|----------------|
| `models.py` | FR-SAP-1/2/3 | `Assumption`, `AssumptionVerdict`, `UnresolvedReason` enum, `FrictionFinding` (canonical payload), `FrictionReport` (versioned artifact), `AVOIDABLE_COST_STAGE` table |
| `extractor.py` | FR-SAP-1 | `extract_assumptions(forward_manifest, skeleton_sources) -> list[Assumption]` |
| `pilot_bore.py` | FR-SAP-4 | overlay builder + `run_project_check` driver + diagnostic file-scoping + robustness/isolation |
| `convention_route.py` | FR-SAP-10 | `detect_conventions` over each skeleton; greenfield fallback |
| `cross_contract.py` | FR-SAP-5 | plan-time `InterfaceContract` consistency (incl. versioned/overload tolerance) |
| `fde.py` | FR-SAP-7 | `FdeQuery` protocol + `ProjectKnowledgeFde` impl + cross-run cache |
| `gate.py` | FR-SAP-8/9/11 | orchestrator: run validators → build ranked report → gating decision (gated off) |
| `report.py` | FR-SAP-3/12 | JSON/MD serialization (`schema_version`), OTel metrics, downstream-prompt injection payload |
| (rules) `workflows/builtin/preflight_rules/rules_sapper.py` | FR-SAP-6 | per-element checks on the `startd8.preflight_rules` seam |

**Touch points in existing code:**
- `workflows/builtin/domain_preflight_workflow.py` — FR-SAP-9: load upstream EMIT artifacts + invoke `gate.run()`.
- `repair/convention.py` `_IDIOM_RULES` — OQ-6: add a declaration-surface `from sqlalchemy.orm import …` rule.
- `plan_ingestion_emitter.py` `DeterministicFileAssembler.render_specs` — OQ-8: verify decorator fidelity in skeletons.
- generation prompt builders (lead/drafter in `contractors/prime_contractor.py`; `micro_prime`) — FR-SAP-12 injection.

---

## 2. Phase sequence (dependency-ordered)

**Phase 0 — Models & schema (foundation; everything depends on it).** `models.py`: the `UnresolvedReason` enum
(`needs_ruling|bore_degraded|authority_absent|omit`), `FrictionFinding` payload (verdict+reason, severity,
expected/found, `avoidable_cost_stage`, `fingerprint`, optional `suggested_fix`/`context_snippet`), the
`AVOIDABLE_COST_STAGE` mapping + tie-break + unmapped-default, and the versioned `FrictionReport`. Pure data +
ranking; fully unit-testable with zero deps. **FR-SAP-1/2/3.**

**Phase 1 — Pilot bore (the lead mechanism).** `extractor.py` (existence assumptions from the manifest) +
`pilot_bore.py`. Overlay **all sibling skeletons + the real codebase** into a per-run temp dir (isolation: no
secrets/`.env`/VCS, no symlink-follow, guaranteed cleanup), run `run_project_check(run_pytest=False)`, **scope
diagnostics to skeleton files**, map to `REFUTED` existence findings. Robustness: syntax-invalid→REFUTED,
size-bound + timeout→`UNRESOLVED(bore_degraded)`, non-Python skeletons filtered to `unavailable`. **The RUN-028
fixture (`strtd8` `app/jobs.py` skeleton) becomes the golden integration test** (replays §0.6). The single
batched overlay (all skeletons + real tree, one `run_project_check`) is a **correctness** requirement here
(§6.1 → FR-SAP-4), not deferred perf. **FR-SAP-4** + plan-scope R2-F1 (mypy-cache reuse only).

**Phase 2 — Convention route.** `convention_route.py` calls `repair/convention.py` `detect_conventions` over each
skeleton (replays §0.7). Land OQ-6 (SQLAlchemy import rule) and OQ-8 (decorator-fidelity check on the skeleton
renderer). Greenfield fallback → 0 findings / `authority_absent`. **FR-SAP-10.**

**Phase 3 — Cross-contract + per-element.** `cross_contract.py` (FR-SAP-5, versioned/overload-tolerant) and
`rules_sapper.py` on the preflight seam composing `element_fillability` + reserved-name + dep-availability
(FR-SAP-6, override-tolerant).

**Phase 4 — FDE interface.** `fde.py`: typed `FdeQuery` protocol (`question`/`evidence` payloads, OMIT≠timeout),
`ProjectKnowledgeFde` reading `ProjectKnowledge` + its `omissions`, cross-run cache keyed by question fingerprint.
Async escalation channel per OQ-5. **FR-SAP-7** (consumer only; NR-1 — no FDE agent).

**Phase 5 — Gate, host integration, delivery.** `gate.py` runs Phases 1–4 validators, dedups, builds the ranked
report; `report.py` writes JSON+MD, emits OTel (`sapper.findings.count{…}`, `unresolved_rate`, `bore_degraded`
alert), and produces the **downstream-injection payload** folded into gen prompts. Wire into
`domain_preflight_workflow` with EMIT absent/stale → loud `UNRESOLVED(authority_absent)`. **FR-SAP-9/11/12.**

**Phase 6 — Gating scaffolding (gated off).** `gate.py` precision-measurement hooks + per-`kind`/`validator_class`
flag plumbing behind `STARTD8_SAPPER_GATING`, defaulting to advisory. No block in v1. **FR-SAP-8** + NR-2.
Plan-scope: CLI `--sapper-only` / `--sapper-min-severity` (R4-F1/R5-F2), timeout tuning (R4-F3).

---

## 3. FR → phase traceability

| FR | Phase | FR | Phase |
|----|-------|----|-------|
| FR-SAP-1 | 0/1 | FR-SAP-7 | 4 |
| FR-SAP-2 | 0 | FR-SAP-8 | 6 |
| FR-SAP-3 | 0 | FR-SAP-9 | 5 |
| FR-SAP-4 | 1 | FR-SAP-10 | 2 |
| FR-SAP-5 | 3 | FR-SAP-11 | 5 |
| FR-SAP-6 | 3 | FR-SAP-12 | 5 |

## 4. Test strategy

- **Phase 0** — pure unit tests (ranking determinism, tie-break, unmapped-kind default, fingerprint stability).
- **Phase 1/2** — golden tests against the **RUN-028 fixture** committed to `tests/fixtures/sapper/`: the
  `Match` existence miss (bore→REFUTED) and the Flask/module-source convention miss (route→REFUTED). These
  *are* the spikes, promoted to regression tests. Requires `mypy` in the test env (CI provisioning — OQ-7).
- **Phase 3–5** — integration test over a synthetic multi-feature plan through `domain-preflight`; assert the
  report artifact validates against the versioned schema and a `REFUTED` line appears in the rendered gen prompt.
- **Degradation matrix** — mypy-absent, EMIT-absent/stale, non-Python skeleton, oversized/syntax-invalid skeleton
  each assert loud `UNRESOLVED` with the correct `reason`, never a silent pass.

## 5. Risks

- **CI mypy dependency** (Phase 1/2 tests). Mitigation: gate golden tests on mypy presence (importorskip), keep
  the compileall floor always-on.
- **Overlay cost on large repos** (OQ-1). Mitigation: evaluate copy-free MYPYPATH overlay before committing to a
  full `copytree`.
- **Prompt-injection coupling** (FR-SAP-12) touches the hot generation path. Mitigation: injection is additive
  (a warning block), behind the advisory contract; no behavior change if the report is empty.

---

## 6. Planning-pass discoveries (APPLIED to requirements v0.6 §0.9)

> These surfaced *while sequencing the build* and change/sharpen the requirements — the reflective-loop payload.
> **Status: all 4 applied** to `SAPPER_PREEXECUTION_VALIDATION_REQUIREMENTS.md` v0.6 (§0.9 + FR-SAP-1/2/4/9).

1. **Batching the bore is a *correctness* requirement, not just latency (upgrades R3-F1).** A skeleton for
   feature A may reference a symbol that feature B's skeleton (also not-yet-generated) defines. For mypy to
   resolve intra-plan cross-references, the overlay must contain **all sibling skeletons together** + the real
   codebase — so the "single batched `run_project_check`" is required for *soundness*, not merely speed. R3-F1
   was triaged to plan-scope-as-perf; planning shows the batching is load-bearing. → **FR-SAP-4 should state the
   overlay scope explicitly** (all skeletons + real tree), and the latency note should be reframed as "batched by
   necessity."
2. **Assumptions extract from the *structured* manifest, not by re-parsing skeleton text.** Two representations
   exist: the structured `ForwardElementSpec`/`InterfaceContract` (for cross-contract, per-element, and the
   convention route's authority lookups) and the rendered skeleton *text* (only the bore needs text → mypy).
   FR-SAP-1 currently lists "emitted skeletons" as a co-equal extraction source; planning shows the structured
   manifest is primary and the skeleton text is bore-only. → **sharpen FR-SAP-1.**
3. **`authority_absent` is overloaded across two emitters** (FR-SAP-9 EMIT-absent and FR-SAP-10 greenfield-no-
   convention). A consumer distinguishing "the pipeline is broken upstream" from "this is a legitimately new
   project" may want separate reasons. → consider splitting the enum (`input_absent` vs `authority_absent`) or
   document the conflation in FR-SAP-2.
4. **`domain-preflight`'s output contract is per-task (`TaskEnrichment`); the Sapper report is cross-task.**
   FR-SAP-9 must add a cross-task output channel to the workflow, not piggyback on `TaskEnrichment`. → note in
   FR-SAP-9.

---

*v0.2 — Plan pass complete. 4 planning discoveries (§6) reflected into requirements v0.6 (§0.9). Ready to build:
Phase 0 (`sapper/models.py`) is the dependency root. Pairs with requirements v0.6.*
