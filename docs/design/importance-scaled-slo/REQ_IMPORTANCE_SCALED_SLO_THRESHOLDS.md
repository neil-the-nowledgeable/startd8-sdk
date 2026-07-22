# Importance-Scaled SLO Thresholds — Requirements

**Version:** 0.6 (Both increments SHIPPED — Increment 2 deployment_mode axis done; OQ-A resolved)
**Date:** 2026-07-22
**Status:** Ready for CRP review
**Owner:** StartD8 SDK / observability (artifact_generator) + ContextCore (manifest, init-from-plan)
**Driver:** Mastodon deterministic-observability pilot, Phase 3 finding — the pipeline *derives*
criticality (0.82) and the service graph (0.85) but **defaults** availability/latency/throughput to
a flat innate table (`99% / 500ms / 100rps`) regardless of how important the service is.

> **Composes with [`../observability-requirement-shaped/`](../observability-requirement-shaped/REQUIREMENTS.md) (#226).**
> This doc owns the **importance** axes — `criticality × deployment_mode` (SLO *tightness*). #226 owns
> the orthogonal **`signal_kind`** axis (which SLIs *exist* — freshness/queue_depth/… for non-request
> services) and reshapes the generator to be requirement-shaped. **They share one table
> (`config/importance_thresholds.yaml`) and one resolver (`_resolve_threshold`, generic over
> `field_name`)** — signal_kind values are `field_name`s that slot under each `<criticality>.<mode>`
> cell. Not rivals; composed by explicit decision (#226 §0.4). Read both before touching the threshold seam.

---

## 0. Planning Insights (Self-Reflective Update)

> Discoveries from reading the actual generator/manifest/init-from-plan code before drafting.
> Six corrections; three shrank the scope, one flipped the primary signal.

| v0.1 Assumption | Planning Discovery | Impact |
|---|---|---|
| Need to build importance-scaling machinery into the generator | `_resolve_threshold` (`artifact_generator_generators.py:106`) already has a **2-tier** resolution (`manifest > default`) with `DerivationTrace` provenance, and `business.default_thresholds` is already manifest-overridable | Scope shrinks to *making the existing default tier importance-aware* — no new resolution machinery. (FR-2) |
| `deployment_mode` can be plumbed from `app.yaml` | In the **pipeline path there is no `app.yaml`** — `deployment.mode` lives only in `scaffold_codegen` (`app.yaml`, backend_codegen). The observability generator has **zero** deployment-mode awareness today | The signal needs a **manifest carrier** (`spec.deployment.mode`) + init-from-plan cue; the `app.yaml` read applies only to the backend_codegen path (FR-4/5/6) |
| `deployment_mode` is the primary signal | `business.criticality` is **already** in `BusinessContext` **and already derived** by init-from-plan (0.82). `_severity_for` already scales *severity* by it | **Criticality-scaled defaults are a zero-plumbing first increment;** `deployment_mode` is an *orthogonal exposure axis* layered on top (FR-8). Primary signal flipped: criticality first, mode as refiner |
| Scaling SLO *targets* by importance is a new pattern | `_CRITICALITY_TO_SEVERITY` already scales alert *severity* by criticality; `DEPLOYMENT_MODE_REQUIREMENTS` OQ-5 already establishes *"mode sets a default"* | This is an *extension of an existing, blessed pattern*, not a novel mechanism — lowers design risk |
| Mode-derived thresholds belong in the manifest | Writing them to `spec.requirements` would make them resolve at `tier="manifest"` — **masquerading as authored** and destroying the author-vs-derivation distinction the pilot exists to measure | Derived thresholds MUST stay in a distinct **`default:importance`** provenance tier, never written back to the manifest (FR-3) |
| The threshold numbers are the hard part | The numbers are a small, overridable config table; the hard part is **provenance honesty + not conflating mode with `deployment_environment`** | Emphasis moves from "pick numbers" to "keep the derivation truthful and the axes separate" (FR-3, NR-2) |

**Resolved open questions (from v0.1):**
- **OQ-1 → Yes, extend the existing default tier.** Do not add a new resolution layer; make the
  `default` branch of `_resolve_threshold` importance-aware.
- **OQ-2 → Criticality first, deployment_mode second.** Criticality is present with no plumbing;
  ship that increment, then add the exposure axis.
- **OQ-3 → Manifest carrier `spec.deployment.mode`, not `app.yaml`, for the pipeline path.**

---

### 0.1 Lessons-Learned Hardening (v0.3)

> Applied the SDK design-docs lessons (`Lessons_Learned/sdk/Design_Docs_LESSONS_LEARNED.md`) before CRP.

- **[Phantom-reference audit]** — every symbol this spec names was grepped in the owning module;
  results in the **Reference Audit** table below. `BusinessContext.deployment_mode` and
  `spec.deployment.mode` are marked **to-be-created**; everything else exists today.
- **[Single-source vocabulary ownership]** — the importance→threshold mapping is declared to live in
  **one** canonical, manifest-overridable table (FR-7), not restated across generators/CLI. Prevents
  a third divergent threshold source (cf. ADR-003's three-generator divergence).
- **[Prune phantom scope]** — "auto-write derived thresholds into the manifest" was cut to a
  Non-Requirement (NR-4): it is architecturally wrong (wrong provenance tier) and would masquerade
  as authored intent.

### 0.2 Design-Principle Hardening (v0.3.1)

> Checked against `startd8-sdk/docs/design-principles/`. Each changed the draft.

- **[Genchi Genbutsu]** — bind to the *authoritative* importance signal, and respect provenance
  boundaries. Forced FR-3 (derived defaults carry an honest `default:importance` tier and are never
  laundered into `tier="manifest"`) and NR-4 (no manifest write-back). Also: the `app.yaml`
  `deployment.mode` is the source of truth *only* on the backend_codegen path (FR-6); the pipeline
  path's authoritative carrier is `spec.deployment.mode` (FR-4).
- **[Accidental-Complexity anti-principle]** — resist adding machinery. Forced FR-2 to *reuse* the
  existing `_resolve_threshold` default tier rather than introduce a parallel resolver, and FR-7 to
  keep **one** overridable table rather than an enumerated per-field/per-mode special-case ladder.
- **[Hitsuzen (derive the determinable)]** — importance-scaled defaults are a *deterministic lookup*
  `(criticality, deployment_mode) → thresholds`, not an LLM call. Locked in FR-2/FR-7 as a pure table.
- **[Context-Correctness-by-Construction]** — `deployment_mode` must reach the generator declared +
  optional, never silently `None`-collapsing into wrong behavior. Forced FR-1 (typed optional field,
  default `None` ⇒ *criticality-only* scaling, an explicit well-defined path — not a crash or a
  silent flat default) and FR-5's "absent cue ⇒ unset, recorded" rule.
- **[Keiyaku / contract]** — the manifest↔generator contract gains one optional field with a
  validated enum; documented in FR-4 so ContextCore and startd8 agree on shape.

---

## Reference Audit (phantom-reference check)

| Symbol / path | Exists today? | Note |
|---|---|---|
| `_resolve_threshold` (`artifact_generator_generators.py:106`) | ✅ | 2-tier resolver, insertion point for FR-2 |
| `_DEFAULT_THRESHOLDS` (`…:40`) | ✅ | flat table to be superseded by the importance table |
| `_CRITICALITY_TO_SEVERITY` (`…:32`) | ✅ | precedent: importance already scales severity |
| `BusinessContext.criticality / .default_thresholds` (`artifact_generator_models.py:61,90`) | ✅ | criticality present; `default_thresholds` overridable |
| `BusinessContext.deployment_mode` | ⛔ to-be-created | FR-1 |
| `_build_context` (`artifact_generator_context.py:376,413`) | ✅ | populates criticality + default_thresholds; wiring point for FR-1 |
| `obs_config.load_default_thresholds` | ✅ | pattern for the overridable importance table (FR-7) |
| `spec.deployment.mode` (ContextCore manifest) | ⛔ to-be-created | FR-4 |
| `infer_init_from_plan` (`init_from_plan_ops.py:514`) | ✅ | criticality/availability cue inference; add mode cue (FR-5) |
| `app.yaml deployment.mode` (`scaffold_codegen/manifest.py:172`) | ✅ | source of truth on backend_codegen path (FR-6) |

---

## 1. Problem Statement

The canonical observability generator resolves SLO thresholds in three effective tiers —
**explicit** (env) > **manifest** (`spec.requirements.*`) > **default**. When the manifest omits a
threshold, the `default` tier returns a **flat** value from `_DEFAULT_THRESHOLDS` (`availability 99`,
`latency_p99 500ms`, `throughput 100rps`) — the **same numbers for a single-user local tool and a
shared multi-tenant production service.**

> **Pilot-corrected premise (v0.5):** the original assumption that pipeline manifests *omit*
> undefined thresholds was **wrong**. The ContextCore pipeline *fabricated* flat values with a
> `contextcore-pipeline-innate` marker, which resolved at `tier="manifest"` and **masked** the
> default tier entirely — so importance scaling never fired. Making it fire required a ContextCore
> change (FR-10 / ADR-004): stop fabricating, leave undefined thresholds absent.

Meanwhile the system already holds two importance signals it does not use for SLO tightness:
1. **`criticality`** — derived by init-from-plan (0.82) and already used for alert *severity*.
2. **`deployment.mode`** (`installed | deployed`) — a first-class, semantically strong exposure
   proxy (`installed` = single-user local SQLite, no auth; `deployed` = shared multi-tenant, auth,
   Postgres, managed migrations, non-loopback, centralized observability) — but confined to the
   backend_codegen path and absent from both the ContextCore manifest and the generator.

| Component | Current state | Gap |
|---|---|---|
| `artifact_generator` default tier | flat `_DEFAULT_THRESHOLDS` | not scaled by any importance signal |
| `BusinessContext` | has `criticality`; no `deployment_mode` | exposure axis unavailable to the generator |
| ContextCore manifest | `business.criticality`, `requirements.*`; no deployment field | no carrier for `deployment_mode` in the pipeline path |
| init-from-plan | infers criticality/availability from cues | no `deployment_mode` cue inference |

**Goal:** when a threshold is not authored, the `default` tier returns an **importance-scaled** value
derived deterministically from `criticality` (always available) and `deployment_mode` (when
declared/inferred) — with honest provenance, and without ever overriding authored intent.

---

## 2. Requirements

- **FR-1 — `deployment_mode` in generator context.** `BusinessContext` gains
  `deployment_mode: Optional[str]` (`"installed" | "deployed" | None`). `_build_context` populates
  it. `None` ⇒ criticality-only scaling (a defined path, never a crash or silent flat default). An
  **out-of-enum** value (e.g. a mode a newer ContextCore emits) is treated as `None` + recorded —
  never a crash (R1-S4; forward-compat).

- **FR-2 — Importance-scaled default tier.** The `default` branch of `_resolve_threshold` selects
  from an importance table keyed on `(criticality, deployment_mode)` instead of flat
  `_DEFAULT_THRESHOLDS`. It runs **only** when manifest/explicit tiers did not supply a value — it
  never overrides authored thresholds. Flat `_DEFAULT_THRESHOLDS` remains the final fallback when no
  importance signal is present.
  - **FR-2a — Monotonicity invariant (R1-F2/R1-S1).** For every scaled field, raising criticality
    and/or moving `installed → deployed` MUST yield a threshold **no looser** than any
    lower-importance cell. `criticality` stays a **live key even when `mode == installed`** — the
    table never collapses `installed+*` into one row (`installed+critical` is strictly tighter than
    `installed+low`). A table that loosens SLOs as importance rises does **not** satisfy FR-2.
  - **FR-2b — Field participation (R1-F6/R1-S2, resolves OQ-B).** **availability** and **latency**
    scale by importance; **throughput stays flat** (`_DEFAULT_THRESHOLDS`) unless authored —
    throughput is a capacity fact, not an importance fact.

- **FR-3 — Honest provenance.** An importance-scaled default emits a `DerivationTrace` with a
  distinct tier (`default:importance`) and a transformation string with a **canonical, parseable
  grammar** (R1-F5), not an illustrative example: `"{deployment_mode|-} + {criticality} → {field}
  {value}"` (e.g. `"deployed + high → availability 99.9"`; `"- + medium → latency_p99 500ms"` when
  mode is unset). Consumers/diff-review can extract `(mode, criticality, field, value)` and see it
  was *derived*, not authored.

- **FR-4 — Manifest carrier.** The ContextCore manifest schema gains optional
  `spec.deployment.mode` with a validated enum (`installed | deployed`). This is the pipeline path's
  authoritative signal (no `app.yaml` there). Absent ⇒ no exposure signal (criticality-only).
  - **FR-4a — Single enum vocabulary source (R1-F7/R1-S5).** The `installed | deployed` literal set
    is declared **once** and shared/derived across the SDK read (FR-1) and the ContextCore validator
    (FR-4), not authored independently per repo — the ADR-003 divergence anti-pattern §0.1 warns
    against. Adding a value in one place surfaces in the other (contract test).

- **FR-5 — init-from-plan cue inference.** `infer_init_from_plan` infers `deployment_mode` from
  plan/requirements cues (e.g. *deployed, production, multi-tenant, shared, SaaS, hosted* ⇒
  `deployed`; *local, single-user, installed, desktop, self-contained* ⇒ `installed`), recording an
  inference + confidence like it does for criticality. **Confidence gate (R1-F1/R1-S3, resolves
  OQ-C):** below a documented floor **C = 0.7** (aligned to the existing 0.82 criticality
  inference), `deployment_mode` stays **unset** (recorded); at or above C it is set. The floor is
  conservative because guessing `deployed` fabricates a tighter error budget the team never agreed
  to, whereas guessing toward `installed`/unset merely forgoes tightening (recoverable by authoring).

- **FR-6 — backend_codegen source of truth.** On the `startd8 generate backend` path,
  `deployment_mode` is read from `app.yaml`'s `deployment.mode` and forwarded to the generator
  context (consistent with it being the SoT there; OQ-5).

- **FR-7 — Single, overridable importance table.** The `(criticality, deployment_mode) → thresholds`
  mapping lives in **one** declarative table, overridable from `spec.observability` via the same
  `obs_config` mechanism as `default_thresholds`. No second/third copy in operator/CLI generators.

- **FR-8 — Incremental delivery.** Increment 1 = criticality-scaled defaults (zero new plumbing;
  `criticality` already in context). Increment 2 = add the `deployment_mode` exposure axis
  (FR-1/4/5/6). Increment 1 must ship value on its own.
  - **✅ STATUS (v0.6): both increments SHIPPED.** Increment 1 — startd8 PR #234 (merged): config-
    driven criticality-scaled SLO defaults; ContextCore PR #27: criticality-scaled sampling/interval
    (`observability_derivation.yaml`) + ADR-005 template de-fabrication (FR-10 family). Increment 2 —
    startd8 PR #247: `BusinessContext.deployment_mode` + `installed`/`deployed` SLO rows; ContextCore
    PR #27: `spec.deployment.mode` model (FR-4) + init-from-plan cue inference (FR-5) +
    deployment-aware sampling/interval. Verified: `installed` yields extremely-forgiving SLOs/sampling.

- **FR-9 — Determinism preserved.** Identical inputs ⇒ byte-identical artifacts. The importance
  table is a pure lookup; no timestamps/ordering/nondeterminism introduced (guards the pilot's
  headline determinism claim).

- **FR-10 — The pipeline MUST NOT fabricate flat SLO placeholder values (ContextCore side).**
  This design assumed manifests *omit* undefined thresholds so FR-2 fires. The Mastodon pilot re-run
  revealed the opposite: the ContextCore pipeline *fabricated* flat values
  (`spec.requirements.availability: "99.9"`, …) with a block-level
  `source: contextcore-pipeline-innate` marker, which the generator resolved at `tier="manifest"` —
  **masking** the importance-scaled default entirely. Therefore undefined SLO requirements MUST be
  left **absent**; **field presence is the authored/derived signal** (the `source` marker is stale —
  never updated on derivation — and lossy — block-level for four fields — so it is NOT a reliable
  signal and is retired). Absent fields flow to FR-2's importance-scaled default; `errorBudget` is
  derived from `availability`; `throughput` defaults flat. **Authoritative decision + full rationale:
  ContextCore [ADR-004 — No fabricated SLO placeholders](../../../../ContextCore/docs/adr/004-no-fabricated-slo-placeholders.md)**
  (`contextcore/docs/adr/004-no-fabricated-slo-placeholders.md`). *This requirement is implemented in
  ContextCore, not startd8; it is recorded here because it is load-bearing for FR-2 to take effect.*

---

## 3. Non-Requirements

- **NR-1** — Does not change the explicit (env) or manifest tiers; **authored thresholds always win.**
- **NR-2** — Does not conflate `spec.deployment.mode` (topology/exposure) with OTel
  `deployment_environment` (telemetry tag). Distinct axes (OQ-5). Mode may inform the tag's default
  elsewhere; that is out of scope here.
- **NR-3** — Does not change the criticality→severity mapping (already importance-scaled).
- **NR-4** — A `default:importance` value MUST NOT surface under `tier="manifest"` in **any**
  emitted or re-ingested artifact — not only the manifest write-back path, but any downstream
  re-serialization that would relabel a derived value as authored (R1-F4/R1-S6/R1-S7). Enforced by a
  generate→re-ingest round-trip test asserting tier stability across all emitted artifacts.
- **NR-5** — Does not derive finer per-endpoint/per-queue SLOs; operates at the service-threshold
  level the generator already uses.
- **NR-6** — Does not require `deployment.mode`; absent ⇒ criticality-only (or flat) scaling.

## 4. Open Questions

- **OQ-A — RESOLVED (v0.6).** Shipped in `config/importance_thresholds.yaml` (SLO) and ContextCore
  `config/observability_derivation.yaml` (sampling/interval), config-overridable (FR-7). `installed`
  is **extremely forgiving** per the operator directive ("a tool a person runs on their own machine
  owes no production SLO"); `deployed`/no-signal keep the criticality scale. Cross-axis monotonic (FR-2a).

  | criticality | **deployed** avail / p99 | **installed** avail / p99 | installed sampling / interval |
  |---|---|---|---|
  | critical | 99.9 / 300ms | 99 / 1s | 0.10 / 60s |
  | high | 99.5 / 400ms | 97 / 2s | 0.05 / 120s |
  | medium | 99 / 500ms | 95 / 3s | 0.01 / 300s |
  | low | 99 / 1s | 90 / 5s | 0.005 / 300s |

  (deployed sampling/interval = the criticality scale: critical 1.0/10s … low 0.01/120s.) The v0.4
  proposal (`installed+critical → 99.5/500ms`, …) was superseded by the more-forgiving values above.
- **OQ-B — RESOLVED (CRP R1 → FR-2b).** Availability + latency scale by importance; **throughput
  stays flat** unless authored (capacity ≠ importance).
- **OQ-C — RESOLVED (CRP R1 → FR-5).** Confidence floor **C = 0.7**; below it `deployment_mode`
  stays unset (recorded). Conservative, because guessing `deployed` fabricates a tighter budget.

---

*v0.6 — Both increments shipped. Increment 2 (deployment_mode axis) done: startd8 PR #247 (SLO
`installed`/`deployed` rows + `BusinessContext.deployment_mode`) + ContextCore PR #27
(`spec.deployment.mode` + cue inference + deployment-aware sampling/interval). OQ-A RESOLVED —
`installed` extremely forgiving (critical 99/1s … low 90/5s; sampling 0.005–0.10). All config-driven
(FR-7), cross-axis monotonic (FR-2a).*

*v0.5 — Post-pilot reflective update. The pilot re-run falsified the "manifests omit thresholds"
premise (they fabricated them), so importance scaling was masked. Added **FR-10** (pipeline must not
fabricate flat SLO placeholders) + corrected the Problem Statement. FR-10 is implemented and owned by
ContextCore **[ADR-004](../../../../ContextCore/docs/adr/004-no-fabricated-slo-placeholders.md)** —
cited here (single-source), not duplicated. Verified end-to-end: pilot `high → 99.5/400ms`
`[default:importance]` (was `99.9/500ms [manifest]`). 10 FRs.*

*v0.4 — Post CRP Round 1: all 7 requirements-side (F) suggestions accepted and merged (FR-1
unknown-value handling, FR-2a monotonicity, FR-2b/OQ-B throughput-flat, FR-3 provenance grammar,
FR-4a single enum source, FR-5/OQ-C 0.7 confidence floor, NR-4 broadened). Dispositions in Appendix
A; round history in Appendix C. OQ-A narrowed to config-only cell values.*

*v0.3.1 — Post planning (6 discoveries, 3 OQs resolved), lessons hardening (3 lessons), and
design-principle hardening (5 principles). 9 FRs, 6 non-requirements, 3 open questions for CRP.*

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
| R1-F1 | FR-5 confidence-threshold acceptance criterion (OQ-C) | CRP R1 | Merged into FR-5 (floor C=0.7); OQ-C marked RESOLVED | 2026-07-22 |
| R1-F2 | Monotonicity invariant on the table | CRP R1 | Added as FR-2a | 2026-07-22 |
| R1-F3 | `installed+*` must keep criticality live | CRP R1 | Folded into FR-2a + OQ-A table expanded | 2026-07-22 |
| R1-F4 | Broaden NR-4 beyond manifest write-back | CRP R1 | NR-4 rewritten to cover any emitted/re-ingested artifact | 2026-07-22 |
| R1-F5 | Canonical transformation-string grammar | CRP R1 | Added to FR-3 (`{mode|-} + {crit} → {field} {value}`) | 2026-07-22 |
| R1-F6 | Fix which fields scale (OQ-B) | CRP R1 | Added as FR-2b (avail+latency scale; throughput flat); OQ-B RESOLVED | 2026-07-22 |
| R1-F7 | Single enum vocabulary source + unknown handling | CRP R1 | FR-4a (single source) + FR-1 (out-of-enum ⇒ None) | 2026-07-22 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-07-22

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-22 00:00:00 UTC
- **Scope**: Dual-document requirements review (requirements-side F-suggestions): ambiguity, missing acceptance criteria, untestable statements, plan↔req inconsistency. Weighted to sponsor asks OQ-A/B/C and provenance-leak paths. Settled §0/§0.1/§0.2 items not relitigated.

**Executive summary (top risks / gaps / opportunities):**

- FR-5 is untestable as written: "records an inference + confidence" but no confidence threshold governs the unset decision (OQ-C is open, so no acceptance criterion exists).
- FR-2 does not state the table's monotonicity property, so any number table (including one that loosens SLOs as criticality rises) technically satisfies it.
- OQ-A's `installed+*` row discards criticality, silently contradicting the FR-8 "criticality always available" spine — an internal inconsistency, not just an open number.
- NR-4 forbids write-back to the manifest but is silent on re-serialization into *other* emitted artifacts — a laundering gap in the non-requirement itself.
- FR-3's transformation-string format is illustrative ("e.g.") with no canonical schema, so provenance consumers can't reliably parse it.
- OQ-B leaves throughput's treatment ambiguous; FR-2 says the table is keyed per-field but no requirement states which fields participate.

**Suggestions (first pass):**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Validation | high | Make FR-5 testable by adding an explicit confidence-threshold acceptance criterion (resolve OQ-C): "below confidence C (starting 0.7), `deployment_mode` stays unset (recorded); at or above C it is set." Currently FR-5 says "recording an inference + confidence" but never states how confidence gates the set/unset decision. | Without a named threshold, FR-5's "absent/ambiguous ⇒ unset" cannot be verified and the implementer must invent the number. | FR-5 body + OQ-C resolution | Test: cue at conf `< C` ⇒ `None`+recorded; `>= C` ⇒ set. |
| R1-F2 | Data | high | Add a monotonicity acceptance property to FR-2/FR-7: for any field, higher criticality and/or `deployed` (vs `installed`) must yield thresholds no looser than a lower-importance cell. FR-2 currently only says "selects from an importance table" without constraining the table's shape. | As written, a table that *loosens* SLOs as importance rises would satisfy FR-2 — the requirement under-specifies the invariant that gives the feature meaning. | FR-2 (or new clause in FR-7) | Property test over the shipped table asserting no importance step loosens any field. |
| R1-F3 | Data | medium | Resolve the OQ-A `installed+*` inconsistency: the proposed row `installed+* → 99/1s` collapses all criticalities, contradicting FR-8's "criticality is always available … criticality-scaled defaults are a zero-plumbing first increment." State that criticality remains a live key even when `mode=installed`. | Internal inconsistency between OQ-A's table and FR-8's spine; an `installed+critical` service would get the same SLO as `installed+low`. | OQ-A table + note referencing FR-8 | Test: `installed+critical` strictly tighter than `installed+low`. |
| R1-F4 | Security | high | Tighten NR-4 to forbid a `default:importance` value from appearing under `tier="manifest"` in ANY emitted/re-ingested artifact, not only "written back into the manifest." NR-4 currently guards only the manifest write-back path, leaving re-serialization laundering (a consumer re-emitting a derived value as authored) out of scope. | The pilot exists to measure author-vs-derivation; a downstream re-serialization that relabels a derived value as `manifest` defeats it just as surely as a direct write-back. | NR-4 body | Round-trip test: generate → re-ingest emitted artifacts → assert no `default:importance` value resolves as `tier="manifest"`. |
| R1-F5 | Interfaces | medium | Give FR-3 a canonical transformation-string schema instead of an "e.g." example. FR-3 shows `"deployed + high → availability 99.9"` as illustrative but defines no grammar, so provenance/diff consumers cannot reliably parse tier or inputs. | An unparseable-by-contract provenance string undercuts FR-3's own goal ("consumers and diff-review can see it was derived"). | FR-3 body | Test: emitted `DerivationTrace.transformation` matches a documented regex/format; fields (mode, criticality, field, value) are extractable. |
| R1-F6 | Data | medium | State explicitly in FR-2/FR-7 which SLO fields participate in importance scaling and which stay flat, resolving OQ-B (recommend: availability + latency scale; throughput flat unless authored). FR-2 describes a per-field table but no requirement fixes throughput's behavior. | Ambiguity: the table shape permits scaling throughput, but throughput is a capacity fact — leaving it unspecified invites divergent implementations. | FR-2 or FR-7 + OQ-B resolution | Test: derived `throughput` equals flat default across all `(criticality,mode)` unless authored. |
| R1-F7 | Interfaces | low | FR-1 and FR-4 both enumerate `installed \| deployed` independently (SDK `BusinessContext` vs ContextCore manifest enum). Add a requirement that the enum vocabulary has a single declared source shared across repos, and specify unknown-value handling (unknown ⇒ criticality-only, recorded). | Two independent enum literals across repos is the ADR-003 divergence anti-pattern the spec's §0.1 explicitly warns against; and neither FR states what happens on an out-of-enum value. | New clause near FR-1/FR-4 (or NR) | Contract test: both repos derive the enum from one source; an unknown mode ⇒ `None`+recorded, no crash. |

**Endorsements / Disagreements:** none (R1 is the first round; no prior untriaged items exist).
