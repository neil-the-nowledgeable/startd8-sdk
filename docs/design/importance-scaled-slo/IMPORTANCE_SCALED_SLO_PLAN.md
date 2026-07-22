# Importance-Scaled SLO Thresholds — Implementation Plan

**Companion to:** [`REQ_IMPORTANCE_SCALED_SLO_THRESHOLDS.md`](./REQ_IMPORTANCE_SCALED_SLO_THRESHOLDS.md) (v0.3.1)
**Date:** 2026-07-22

This plan was written *before* the requirements were finalized and fed the §0 Planning Insights.
It is organized by the two increments in FR-8 so Increment 1 ships value alone.

---

## Increment 1 — Criticality-scaled defaults (zero new plumbing)

`business.criticality` is already in `BusinessContext` and already populated by `_build_context`.
This increment makes the `default` tier criticality-aware. It satisfies FR-2, FR-3, FR-7, FR-8, FR-9
for the criticality axis with **no manifest or init-from-plan changes**.

| Step | File · anchor | Change | FR |
|---|---|---|---|
| 1.1 | `observability/artifact_generator_generators.py:40` | Add `_IMPORTANCE_THRESHOLDS: Dict[Tuple[str, Optional[str]], Dict[str,str]]` keyed on `(criticality, deployment_mode)`; keep `_DEFAULT_THRESHOLDS` as the no-signal fallback. **Populate `availability`+`latency_p99` only; leave `throughput` out (flat) unless authored (R1-S2/FR-2b).** | FR-2, FR-2b, FR-7 |
| 1.2 | `…_generators.py:127` (`_resolve_threshold` default branch) | Replace the flat lookup with `_select_importance_default(business.criticality, business.deployment_mode, field_name)`, falling back to `business.default_thresholds or _DEFAULT_THRESHOLDS` | FR-2, FR-1 (reads `deployment_mode`, `None`-safe) |
| 1.3 | same | Emit `DerivationTrace(tier="default:importance", transformation="{crit}+{mode} → {field} {value}")` when the importance table hits; keep `tier="default"` for the flat fallback | FR-3 |
| 1.4 | `observability/obs_config.py` (`load_default_thresholds` sibling) | Add `load_importance_thresholds(manifest)` so `spec.observability` can override the table (single overridable source) | FR-7 |
| 1.5 | `tests/unit/observability/test_artifact_generator.py` | Cases: `high` ⇒ tighter than flat; `medium` ⇒ unchanged; authored `spec.requirements.availability` still wins (tier=manifest); byte-identical across two runs. **+ monotonicity property test (R1-S1); + `throughput` flat across all cells unless authored (R1-S2); + generate→re-ingest round-trip asserting no `default:importance` value resolves as `tier="manifest"` (R1-S7/NR-4)** | FR-2/2a/2b/3/9, NR-1, NR-4 |

**Increment 1 acceptance:** a `criticality: high` manifest with no `requirements.availability` yields
a tighter derived availability than `99`, tagged `default:importance`; a manifest that *authors*
availability is unchanged (tier=manifest).

---

## Increment 2 — deployment_mode exposure axis

Adds the orthogonal signal and its two carriers (manifest for the pipeline path, `app.yaml` for
backend_codegen).

| Step | File · anchor | Change | FR |
|---|---|---|---|
| 2.1 | `observability/artifact_generator_models.py:61` (`BusinessContext`) | Add `deployment_mode: Optional[str] = None` | FR-1 |
| 2.2 | `observability/artifact_generator_context.py:376` (`_build_context`) | Populate `ctx.deployment_mode` from `spec.deployment.mode` (manifest). **Out-of-enum value ⇒ `None` + recorded, never crash (R1-S4/FR-1 forward-compat).** | FR-1, FR-4 |
| 2.3 | **ContextCore** `models/core.py` (new `DeploymentSpec`; add to spec) | Optional `spec.deployment.mode` enum (`installed\|deployed`) with a `field_validator`, **derived from the one shared enum vocabulary (R1-S5/FR-4a)** | FR-4, FR-4a, Keiyaku |
| 2.4 | **ContextCore** `cli/init_from_plan_ops.py:514` (`infer_init_from_plan`) | Add cue regex → set `spec.deployment.mode` + `add_inference(..., "plan:deployment_mode_cue", conf)`; **below confidence floor `C=0.7` ⇒ unset (recorded) (R1-S3/FR-5)** | FR-5 |
| 2.5 | `scaffold_codegen`/`cli_generate.py:350` | Forward resolved `deployment_mode` into the observability generation context on the backend path | FR-6 |
| 2.6 | table (1.1) | Extend `_IMPORTANCE_THRESHOLDS` keys to real `(criticality, deployment_mode)` pairs per OQ-A. **Do NOT collapse `installed+*` — keep `criticality` a live key (`installed+critical` tighter than `installed+low`); preserve monotonicity (R1-S1/FR-2a).** | FR-2, FR-2a |
| 2.7 | ContextCore + SDK tests | init-from-plan cue inference; manifest enum validation; `deployed+high` tighter than `installed+high`; `None` mode ⇒ criticality-only | FR-5, FR-4, FR-1 |

**Increment 2 acceptance:** `spec.deployment.mode: deployed` + `criticality: high` yields tighter
SLOs than `installed + high`; a plan mentioning "multi-tenant production service" infers
`deployed`; absent ⇒ criticality-only.

---

## Cross-repo dependency & sequencing

- Increment 1 is **startd8-sdk-only** — ship first, independently.
- Increment 2 spans **ContextCore** (2.3, 2.4) and **startd8-sdk** (2.1, 2.2, 2.5). Land the SDK
  `BusinessContext.deployment_mode` read (2.1/2.2) first (tolerant of absent **and unknown** field
  values — R1-S4), then the ContextCore manifest field + cue (2.3/2.4) — so neither repo
  hard-depends on an unreleased other, and a newer ContextCore mode string can never crash an older SDK.
- **Single enum vocabulary source (R1-S5):** the `installed|deployed` literal set is declared once
  and shared/derived across FR-1 (SDK read) and FR-4 (ContextCore validator) — not authored twice.
- No change to the manifest↔generator contract beyond one **optional** field ⇒ backward compatible.

## Risks / guards

- **Provenance laundering (NR-4, broadened R1-S6):** enforce via a test asserting a `default:importance`
  value never surfaces under `tier="manifest"` in **any** emitted artifact (generator outputs +
  exported specs), not only `.contextcore.yaml`. Plus the generate→re-ingest round-trip (Step 1.5).
- **Axis conflation (NR-2):** a test asserting `spec.deployment.mode` does not set OTel
  `deployment_environment`.
- **Determinism (FR-9):** reuse the pilot's determinism harness on a fixture manifest.
- **Number bikeshedding (OQ-A):** the table is config (FR-7); ship a documented default, iterate in
  review — do not block Increment 1 on final numbers.

## Traceability

FR-1→2.1/2.2 · FR-2→1.1/1.2/2.6 · FR-3→1.3 · FR-4→2.3/2.2 · FR-5→2.4 · FR-6→2.5 · FR-7→1.4 ·
FR-8→(Increment split) · FR-9→1.5 guard · **FR-10→ContextCore ADR-004 (no startd8 step — it is the
load-bearing ContextCore precondition that makes FR-2 fire; see ContextCore PR #25)**. Every FR has a
step (or a cross-repo owner); every step traces to an FR.

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-S1 | Don't collapse `installed+*`; keep criticality live + monotonicity | CRP R1 | Step 2.6 + monotonicity test in Step 1.5 | 2026-07-22 |
| R1-S2 | `throughput` flat by default + negative test | CRP R1 | Step 1.1 (populate avail+latency only) + Step 1.5 test | 2026-07-22 |
| R1-S3 | Pin inference-confidence floor 0.7 | CRP R1 | Step 2.4 (C=0.7) | 2026-07-22 |
| R1-S4 | Unknown-mode ⇒ None + recorded (forward-compat) | CRP R1 | Step 2.2 + Cross-repo sequencing | 2026-07-22 |
| R1-S5 | Single enum vocabulary source | CRP R1 | Step 2.3 + Cross-repo sequencing note | 2026-07-22 |
| R1-S6 | Broaden NR-4 guard to all emitted artifacts | CRP R1 | Risks/guards → Provenance laundering | 2026-07-22 |
| R1-S7 | Generate→re-ingest round-trip test | CRP R1 | Step 1.5 | 2026-07-22 |
| Asks 1-5 | Sponsor focus answers (OQ-A/B/C, sequencing, laundering) | CRP R1 | OQ-B/OQ-C resolved in requirements v0.4; OQ-A narrowed to config cell values | 2026-07-22 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-07-22

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-22 00:00:00 UTC
- **Scope**: Dual-document plan review (plan-side S-suggestions). Weighted to sponsor focus asks OQ-A/B/C, cross-repo sequencing decoupling, and provenance-leak paths. Settled §0/§0.1/§0.2 items not relitigated.

**Sponsor focus asks (answered before standard suggestions):**

- **Ask 1 — OQ-A number table (defensible? config-overridable the right home?):**
  - **Summary answer:** Partial — config-overridable is clearly correct; the *starting* numbers are mostly defensible but have two soft spots (the `installed+*` collapse and the `deployed+medium 500ms` cliff).
  - **Rationale:** Config-as-home is right per FR-7 and Step 1.4 (`load_importance_thresholds`) — numbers are review-tunable without a code release, and the plan explicitly de-risks bikeshedding under "Risks / guards → Number bikeshedding". But the proposed grid (`REQ` OQ-A) folds all `installed+*` into one `99/1s` row, discarding criticality entirely once mode=installed — that contradicts the "criticality always available" spine (FR-8) and means a `installed+critical` desktop tool gets the same SLO as `installed+low`. Also `deployed+high 300ms` → `deployed+medium 500ms` is a 200ms cliff on one criticality step; latency ladders usually want monotonic-but-smoother steps.
  - **Assumptions / conditions:** Increment 1 ships criticality-only rows; the full `(criticality×mode)` grid only lands at Step 2.6, so the `installed+*` collapse is a Step-2.6 concern, not an Increment-1 blocker.
  - **Suggested improvements:** In Step 2.6, keep criticality as a live key even when `mode=installed` (do not collapse the row); document the intended monotonicity property of the table as an acceptance check (see R1-S1).
- **Ask 2 — OQ-B should `throughput` scale by importance:**
  - **Summary answer:** No — leave `throughput` flat unless authored; scale only availability + latency by default.
  - **Rationale:** Throughput is a capacity/load fact, not an exposure/importance fact — a high-criticality service can legitimately be low-QPS. Deriving a throughput floor from importance risks emitting an SLO the service cannot meet and cannot control, undermining the pilot's credibility. The plan's table shape (Step 1.1, `Dict[str,str]` per field) already permits per-field opt-out.
  - **Assumptions / conditions:** none.
  - **Suggested improvements:** Encode "throughput excluded from importance scaling by default" as a table-population rule in Step 1.1/2.6 and a negative test in Step 1.5 (see R1-S2).
- **Ask 3 — OQ-C FR-5 inference-confidence threshold (conservative vs eager):**
  - **Summary answer:** Conservative — leave `deployment_mode` unset below a documented floor; tightening SLOs on a guess is the more expensive error.
  - **Rationale:** FR-5 already prefers "absent/ambiguous ⇒ unset (recorded)". Guessing `deployed` tightens SLOs (OQ-C's own framing), which can fabricate an error budget the team never agreed to; guessing wrong toward `installed` merely loses tightening (recoverable via authoring). Asymmetric cost ⇒ conservative floor. The plan should name a concrete number so Step 2.4/2.7 is testable.
  - **Assumptions / conditions:** criticality-scaling still runs when mode is unset, so "unset" is not "no SLO".
  - **Suggested improvements:** Pin a starting confidence floor (e.g. 0.7, aligned to the existing 0.82 criticality inference) in Step 2.4 and assert it in Step 2.7 (see R1-S3).
- **Ask 4 — cross-repo sequencing actually decoupled?:**
  - **Summary answer:** Mostly — the "SDK-reads-optional-first" ordering is sound, but there is a hidden coupling in the *inference* half (Step 2.4 ContextCore cue) and in shared enum vocabulary.
  - **Rationale:** See R1-S4/R1-S5 — the enum string set (`installed|deployed`) is authored in two repos (SDK `BusinessContext` FR-1 read vs ContextCore `DeploymentSpec` FR-4 validator) with no shared contract, and the plan does not state what the SDK does when it reads an *unknown* mode string a newer ContextCore might emit.
  - **Suggested improvements:** R1-S4 (forward-compat unknown-mode handling), R1-S5 (single enum vocabulary source of truth).
- **Ask 5 — does `default:importance` + NR-4 close all provenance-laundering leak paths?:**
  - **Summary answer:** No — the tier + no-write-back closes the primary path, but `load_importance_thresholds` overrides (Step 1.4) and downstream re-serialization are unguarded leak paths.
  - **Rationale:** See R1-S6/R1-S7. A `spec.observability` override (FR-7/Step 1.4) still resolves through the *default* tier, so an operator override is correctly `default:importance` — good. But nothing asserts a consumer that reads a derived value cannot re-emit it into a manifest `spec.requirements` block (re-serialization laundering), and the NR-4 guard as planned only checks the *emitted `.contextcore.yaml`*, not intermediate artifact-generator outputs.
  - **Suggested improvements:** R1-S6 (extend the NR-4 guard to all emitted artifacts, not just `.contextcore.yaml`), R1-S7 (add a round-trip test that a `default:importance` value never re-enters as `tier="manifest"`).

**Executive summary (top risks / gaps / opportunities):**

- The `installed+*` table row collapses criticality, contradicting the FR-8 "criticality always live" spine — a design gap that only surfaces at Step 2.6.
- No plan step names the OQ-C confidence floor, so Step 2.7's "cue inference" test is currently unverifiable (no threshold to assert).
- The `installed|deployed` enum is authored independently in two repos with no shared vocabulary source — drift risk (echoes ADR-003's three-generator divergence the spec explicitly cites).
- Cross-repo ordering handles *absent* field well but is silent on *unknown* field values a newer ContextCore may emit (forward-compat gap).
- NR-4 guard scope is narrow (`.contextcore.yaml` only); re-serialization of derived values into other artifacts is an unguarded laundering path.
- Opportunity: the determinism harness reuse (Risks / guards → Determinism) is 80% there — extend it to assert table monotonicity for free.
- Throughput should be excluded from importance scaling by default (OQ-B) — cheap negative test, high credibility payoff.

**Suggestions (first pass):**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Data | high | In Step 2.6, do NOT collapse all `installed+*` into one row; keep `criticality` as a live table key under `mode=installed` (e.g. `installed+critical` tighter than `installed+low`). Document the table's intended monotonicity (higher criticality and/or `deployed` ⇒ never-looser thresholds) as an invariant. | The OQ-A proposal folds `installed+*` into a single `99/1s` row, discarding the always-available criticality signal the whole FR-8 spine relies on. | Increment 2 table, Step 2.6 ("Extend `_IMPORTANCE_THRESHOLDS` keys") | Unit test: for fixed mode, tightening criticality never loosens any field; `installed+critical` ≠ `installed+low`. |
| R1-S2 | Data | medium | Add an explicit table-population rule that `throughput` is excluded from importance scaling by default (flat unless authored), per OQ-B, and a negative test. | Throughput is a capacity fact, not an importance fact; deriving a throughput floor risks emitting an unmeetable, uncontrollable SLO. | Step 1.1 (`_IMPORTANCE_THRESHOLDS` construction) + Step 1.5 test list | Test: derived artifact's `throughput` equals flat `_DEFAULT_THRESHOLDS` across all `(criticality,mode)` unless `spec.requirements` authors it. |
| R1-S3 | Validation | high | Pin a concrete starting inference-confidence floor for FR-5 (e.g. `0.7`) in Step 2.4, below which `deployment_mode` stays unset (recorded), and assert it in Step 2.7. | OQ-C is currently a question with no number; Step 2.7's cue-inference test cannot verify "leave unset below threshold" without a named threshold. Conservative floor matches the asymmetric cost of guessing `deployed`. | Step 2.4 change cell + Step 2.7 test row | Test: a plan cue at confidence `< floor` yields `deployment_mode=None` with a recorded inference; `>= floor` sets it. |
| R1-S4 | Interfaces | high | State the SDK's behavior when `BusinessContext` / `_build_context` reads a `deployment.mode` string outside the known enum (e.g. a value a newer ContextCore emits): treat unknown as unset (criticality-only) + record, never crash. | Cross-repo "SDK reads optional first" decouples *absence* but not *unknown values*; a newer ContextCore mode string would otherwise be a hidden hard dependency / crash. | Step 2.2 (`_build_context` populate) and "Cross-repo dependency & sequencing" | Test: `_build_context` with `spec.deployment.mode: "canary"` (unknown) ⇒ `deployment_mode=None`, no exception, recorded. |
| R1-S5 | Interfaces | medium | Designate a single source of truth for the `installed\|deployed` enum vocabulary shared across the SDK read (FR-1/Step 2.1) and the ContextCore validator (FR-4/Step 2.3), rather than authoring the literal set independently in each repo. | The spec itself cites ADR-003's three-generator divergence as the anti-pattern; two independent enum literals is the same failure in miniature. | "Cross-repo dependency & sequencing" section + Steps 2.1/2.3 | Grep/contract test: both repos derive the enum from one declared list (or a documented shared constant); adding a value in one flags the other. |
| R1-S6 | Security | high | Broaden the NR-4 provenance-laundering guard (Risks / guards) beyond "never written to the emitted `.contextcore.yaml`" to cover ALL emitted artifacts (generator outputs, exported specs), asserting a `default:importance` value never surfaces under `tier="manifest"` anywhere downstream. | The planned guard checks only `.contextcore.yaml`; re-serialization into other artifacts is an unguarded laundering path (sponsor Ask 5). | "Risks / guards → Provenance laundering (NR-4)" | Test: scan every emitted artifact for any threshold whose value matches a `default:importance` derivation and assert its tier tag stays `default:importance`. |
| R1-S7 | Validation | medium | Add a round-trip (re-serialization) test: feed a manifest with no authored thresholds through generation, capture a `default:importance` value, re-ingest the emitted artifacts, and assert the value never re-enters resolution as `tier="manifest"`. | NR-4 forbids write-back but nothing tests the downstream re-ingest loop that would launder a derived value into authored provenance. | Step 1.5 test list (extend) | Automated round-trip test in `test_artifact_generator.py` asserting tier stability across a generate→re-ingest cycle. |

**Endorsements / Disagreements:** none (R1 is the first round; no prior untriaged items exist).

---

## Requirements Coverage Matrix — R1

Analysis only (not triage). Maps each requirement to the plan step(s) that address it.

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-1 (`deployment_mode` in `BusinessContext`, `None`-safe) | 2.1, 2.2 | Full | Unknown-value (non-enum) handling unspecified — see R1-S4. |
| FR-2 (importance-scaled default tier) | 1.1, 1.2, 2.6 | Full | Table monotonicity / `installed+*` criticality collapse — see R1-S1. |
| FR-3 (honest `default:importance` provenance) | 1.3 | Full | — |
| FR-4 (manifest carrier `spec.deployment.mode` + enum) | 2.3, 2.2 | Full | Enum vocabulary authored in two repos — see R1-S5. |
| FR-5 (init-from-plan cue inference, unset below confidence) | 2.4 | Partial | No concrete confidence floor (OQ-C) — untestable as written; see R1-S3. |
| FR-6 (backend_codegen `app.yaml` source of truth) | 2.5 | Full | — |
| FR-7 (single overridable importance table) | 1.4 | Full | Override still routes through default tier (correct) but not asserted — see R1-S6. |
| FR-8 (incremental delivery; Increment 1 ships alone) | Increment 1 / Increment 2 split | Full | — |
| FR-9 (determinism preserved) | 1.5 guard, Risks/guards → Determinism | Full | Could also assert table monotonicity via same harness (opportunity, R1-S1). |
| NR-1 (authored thresholds always win) | 1.5 test | Full | — |
| NR-2 (mode ≠ `deployment_environment`) | Risks/guards → Axis conflation | Full | — |
| NR-3 (criticality→severity unchanged) | (out of scope by design) | Full | — |
| NR-4 (no manifest write-back) | Risks/guards → Provenance laundering | Partial | Guard scoped to `.contextcore.yaml` only; re-serialization path unguarded — see R1-S6/R1-S7. |
| NR-5 (no per-endpoint SLOs) | (out of scope by design) | Full | — |
| NR-6 (mode optional) | 2.2, FR-1 `None` path | Full | — |
| OQ-A (number table) | 2.6, Risks/guards → Number bikeshedding | Partial | `installed+*` collapse + latency cliff — see R1-S1. |
| OQ-B (throughput scaling) | (unresolved) | Partial | Plan does not encode the flat-throughput default — see R1-S2. |
| OQ-C (confidence threshold) | 2.4 (unresolved) | Partial | No pinned floor — see R1-S3. |
