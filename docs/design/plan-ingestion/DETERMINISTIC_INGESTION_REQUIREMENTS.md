# Deterministic Plan Ingestion — Functional Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-03
**Status:** Draft (pre-implementation)
**Supersedes/amends:** `docs/PLAN_INGESTION_REQUIREMENTS.md` REQ-PI-011/012 (Route Parity / Route Selection); reconciles `GOLDEN_SEED_REQUIREMENTS.md` data-flow and `SEED_UNIFICATION_REQUIREMENTS.md` REQ-SU-102.

---

## 0. Planning Insights (Self-Reflective Update)

> This section documents what changed between v0.1 (pre-planning) and v0.2 (post-planning).
> The planning pass read the actual code paths and revealed that the deterministic
> machinery this initiative needs **already exists** — it is wired only as a post-failure
> fallback, not as the default. That collapses the scope from "build deterministic ingestion"
> to "promote existing heuristic paths to default + gate the LLM paths behind opt-in flags."

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| TRANSFORM needs a new deterministic YAML generator | `_heuristic_transform_content()` (`plan_ingestion_parsing.py:432`) already emits byte-equivalent YAML (`title=f.name`, `task_description=f.description or f.name`, `context.target_files`) — and is *already used* as the on-error fallback (`workflow.py:4331`) | FR-1 narrowed: no new generator; flip the default + add opt-in flag |
| ASSESS needs to be demoted to a cheap/local model, or 5 of 7 dims hand-computed | `_heuristic_assess_complexity()` (`plan_ingestion_parsing.py:246`) already computes **all 7 dimensions + composite** deterministically, and is *already used* as the on-failure fallback (`workflow.py:4220`) | FR-2 narrowed: eliminate the ASSESS LLM call entirely by defaulting to the existing heuristic scorer — no model demotion, no new scoring |
| Folding ASSESS into PARSE saves a round-trip | Unnecessary — the LLM round-trip can be removed outright since the score is telemetry-only and a deterministic equivalent exists | OQ-1 resolved: do **not** fold into PARSE; just stop calling the ASSESS LLM by default |
| Routing is "always prime" cleanly per REQ-SU-102 | **Correction (found during S4 implementation):** the dangerous `route → artisan` reassignment is ALREADY gone — `route` is only ever set to `ContractorRoute.PRIME` (`workflow.py:1682`). What remains is **misleading drift**: a stale comment at `workflow.py:4243–4246` ("Override routing to artisan…"), a `low_quality_policy="bias_artisan"` default that no longer biases to artisan (it's just the advisory-warn branch), and a `force_route` config with no routing effect. | FR-4 downgraded: not a latent bug — comment/naming cleanup so a future dev can't "restore" the harmful behavior the comment still describes |
| Only `PLAN_INGESTION_REQUIREMENTS.md` is stale | `GOLDEN_SEED_REQUIREMENTS.md` models the pipeline as "PARSE → TRANSFORM → REFINE produces the seed," which misrepresents reality (tasks derive from PARSE features; TRANSFORM YAML is read only for optional `shared_contracts`) | FR-5 broadened to reconcile three docs, not one |
| The transform YAML is dead and could be deleted | It is still consumed by Artisan `context_seed` phases (`plan.py:205`, `shared.py:467`), by REFINE (reviews `doc_path`), by `shared_contracts` scavenging (`emitter.py:387`), and by standalone scripts (`run_auto_decompose_pipeline.py`, `enrich_prime_tasks.py`, `run_artisan_contractor.py`) | FR-1 hardened: the YAML **artifact must still be written** (same path, valid schema) — only its *generator* changes from LLM to deterministic |

**Resolved open questions:**
- **OQ-1 → Eliminate, don't fold.** ASSESS's LLM call is removed (default to heuristic scorer); no PARSE-merge needed.
- **OQ-2 → Keep the LLM transform reachable.** A `enable_llm_transform` flag (default `false`) preserves the LLM path for the one case where it adds value: synthesizing a `shared_contracts:` block. When off (default), `_heuristic_transform_content` writes the YAML at zero LLM cost.
- **OQ-3 → No seed-quality regression expected.** The emitted seed already derives tasks from PARSE features, so removing the TRANSFORM and ASSESS LLM calls cannot change seed task content. The analyzed run's `seed_quality_score=0.9667` is produced by PARSE + deterministic enrichment, both unchanged.

*Heuristic check: ~50% of v0.1 requirements were narrowed or reframed by planning. Per the skill's rule of thumb, the v0.1 draft was premature — which is the loop working: the corrections cost a document edit instead of a refactor.*

---

## 1. Problem Statement

Plan ingestion runs three LLM phases on the critical path — PARSE, ASSESS, TRANSFORM — followed by deterministic enrichment and EMIT. Empirical analysis of a real run (element-registry `IMPLEMENTATION_PLAN.md`, 32 features) shows two of those three LLM calls produce output that is either discarded or redundant:

| Phase | Cost | % ingestion LLM cost | Latency | % latency | Output actually used? |
|-------|------|----------------------|---------|-----------|-----------------------|
| PARSE | $0.1595 | 37.8% | 103.5s | 28.8% | ✅ Authoritative — drives the seed |
| ASSESS | $0.0092 | 2.2% | 7.9s | 2.2% | ❌ Route discarded (always prime); composite is telemetry-only |
| **TRANSFORM** | **$0.2531** | **60.0%** | **247.4s** | **68.9%** | ❌ Redundant — seed derives tasks from PARSE features; YAML read only for optional `shared_contracts` (absent in this run) |

**Evidence the ASSESS route is dead:** the run's own ASSESS reasoning states *"The composite score of 58 routes this to artisan,"* yet the emitted route is `prime` — the LLM's decision was overridden.

**Evidence TRANSFORM is redundant:** all 32 task descriptions in the LLM YAML are byte-identical to the emitted seed's descriptions, because both equal `feature.description`. The 64k-token-budget call reproduced PARSE output verbatim.

Combined, ASSESS + TRANSFORM are **62.2% of ingestion LLM cost and ~71% of ingestion LLM latency** for output the active (prime) path does not consume.

The documented requirements have not kept pace: they describe live Artisan/Prime routing (REQ-PI-011/012) and a TRANSFORM-produces-the-seed data flow that no longer match the code.

### Gap table

| Component | Documented behavior | Actual behavior |
|-----------|---------------------|-----------------|
| Routing | Complexity score selects Artisan vs Prime; route logged with reason (REQ-PI-011/012) | Always `prime`; Artisan ON HOLD; a stale override can still flip to the dead artisan path |
| ASSESS | Produces the routing decision | Route discarded; composite kept for telemetry only; deterministic equivalent exists as fallback |
| TRANSFORM | "PARSE → TRANSFORM → REFINE produces the enriched seed" (GOLDEN_SEED) | Seed tasks derive from PARSE features; TRANSFORM YAML is non-authoritative; deterministic generator exists as fallback |
| Task source of truth | Unspecified | PARSE features via `_derive_tasks_from_features` |

---

## 2. Requirements

### FR-1: TRANSFORM deterministic by default
The TRANSFORM phase MUST default to deterministic YAML generation via `_heuristic_transform_content(parsed_plan, route)`, incurring **zero LLM cost**.
- The YAML artifact MUST continue to be written to the same path (`plan-ingestion-tasks.yaml`) with the same schema, preserving all existing consumers (Artisan `context_seed`, REFINE document target, `shared_contracts` scavenging, standalone scripts).
- The LLM transform path (`_phase_transform`) MUST remain reachable via an opt-in config flag `enable_llm_transform` (default `false`).
- When `enable_llm_transform=false`, no transformer agent is resolved and no transform LLM call is made.

### FR-2: ASSESS telemetry-only and LLM-free by default
The ASSESS phase MUST default to deterministic complexity scoring via `_heuristic_assess_complexity(parsed_plan, ...)`, incurring **zero LLM cost**.
- The 7-dimension `ComplexityScore` + composite MUST still be produced and recorded in diagnostics/telemetry (Kaizen seed-fitness consumption is unchanged).
- The LLM assess path (`_phase_assess`) MUST remain reachable via an opt-in config flag `enable_llm_assess` (default `false`).
- The `route` field MUST be `prime` regardless of score (no behavior change; see FR-4).

### FR-3: PARSE is the documented single source of truth for tasks
The requirements MUST state explicitly that, for the prime path, the seed's tasks are derived from PARSE `features` (`_derive_tasks_from_features`: `title=feature.name`, `task_description=feature.description`), and that the TRANSFORM YAML is **not** the authoritative task source.

### FR-4: Remove misleading artisan-routing drift (comment/naming only)
**Revised after implementation discovery:** the harmful `route → artisan` reassignment does **not** exist in code (`route` is only ever `ContractorRoute.PRIME`). This requirement is therefore narrowed to removing the *misleading drift* that could lead a future dev to reintroduce the harmful behavior:
- The stale comment at `plan_ingestion_workflow.py:4243–4246` ("Override routing to artisan unless the user explicitly forced a route") MUST be rewritten to describe the actual advisory-only behavior.
- `low_quality_policy="bias_artisan"` MUST be documented (and its log/messages clarified) as advisory-warn — it does NOT bias to artisan. (Renaming the value is deferred — it's a public config key; see OQ-7.)
- `force_route` MUST be documented as no-op for routing (retained for backward-compat per FR-7).
Low-quality plans remain on the prime path (already true). The low-quality signal is retained for telemetry/policy.

### FR-5: Documentation reconciliation
The following docs MUST be reconciled to match actual behavior:
- `docs/PLAN_INGESTION_REQUIREMENTS.md`: mark REQ-PI-011 (Route Parity) and REQ-PI-012 (Route Selection Logging) as superseded by REQ-SU-102; update the data-flow diagram to drop the Artisan branch.
- `GOLDEN_SEED_REQUIREMENTS.md`: correct the pipeline data-flow to show PARSE features → deterministic derivation as the seed-task source.
- `SEED_UNIFICATION_REQUIREMENTS.md`: mark REQ-SU-102 acceptance criteria (heuristic override removal) as completed by FR-4.

### FR-6: Cost & latency telemetry assertion
The `plan-ingestion-diagnostic.json` MUST record, per phase, whether the deterministic or LLM path was used (`metadata.deterministic: true|false`), so the cost reduction is observable across runs.

### FR-7: Config cleanup (non-breaking)
Stale routing config fields (`complexity_threshold`, `force_route`, `low_quality_policy="bias_artisan"`) MUST be documented as deprecated. They MUST be retained for backward compatibility but MUST NOT influence routing. `low_quality_policy`'s `"bias_artisan"` default MUST be documented as a no-op.

---

## 3. Non-Requirements

- **NOT** deleting the LLM TRANSFORM/ASSESS code paths — they remain behind opt-in flags.
- **NOT** deleting the `plan-ingestion-tasks.yaml` artifact or changing its schema/path.
- **NOT** modifying PARSE, REFINE, deterministic enrichment, micro-ingest, or EMIT logic.
- **NOT** reviving or modifying the Artisan pipeline (ON HOLD).
- **NOT** changing seed schema, seed-quality scoring, or downstream Prime Contractor behavior.
- **NOT** implementing `shared_contracts` synthesis in this initiative (the `enable_llm_transform` flag merely preserves the existing path that *can* produce it).

---

## 4. Open Questions

- **OQ-4:** Should `enable_llm_assess`/`enable_llm_transform` be surfaced as CLI flags and `.cap-dev-pipe/pipeline.env` knobs, or config-only? (Leaning config-only for v1; CLI later.)
- **OQ-5:** Do any existing tests assert that ASSESS/TRANSFORM make an LLM call (e.g. mock `agent.generate`)? Those tests will need updating to the deterministic default. (Planning pass flagged `tests/unit/test_plan_ingestion_workflow.py` for audit.)
- **OQ-6:** Should REFINE remain pointed at the (now deterministic) YAML, or be re-pointed at the richer enriched seed? Out of scope here, but worth a follow-up — REFINE currently reviews a document whose task content is non-authoritative.
- **OQ-7:** Rename `low_quality_policy="bias_artisan"` to a non-misleading value (e.g. `"warn"`)? Deferred — it's a public config key with backward-compat implications; for now document it as advisory-warn and clarify log wording (FR-4).

---

*v0.2 — Post-planning self-reflective update. 3 requirements narrowed (FR-1, FR-2), 1 added from a discovered latent bug (FR-4), 1 broadened (FR-5), 3 open questions resolved (OQ-1/2/3).*
