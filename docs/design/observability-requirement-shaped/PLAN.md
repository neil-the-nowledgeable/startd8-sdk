# Implementation Plan — Requirement-Shaped, Service-Kind-Aware Observability (#226)

**Version:** 1.2 (matches REQUIREMENTS v0.5 — CRP R1 applied)
**Date:** 2026-07-22
**Companion:** `REQUIREMENTS.md`

> Seam decision: **invert the core triplet from "always RED, patch exceptions" to
> "derive per resolved SLI-kind set; RED is just the request-serving fallback."**
> Promote the existing contract-driven `_EXTENDED_PER_SERVICE_GENERATORS` gate
> (`artifact_generator.py:200/556`) to govern the triplet, and **delete** the
> unconditional synthesis in `_ensure_red_coverage`. Everything else is a table
> lookup (kind→profile, signal_kind→series, signal_kind→thresholds) — one general
> rule, not per-kind `if` branches. The single justified branch is the SLI-kind
> gate inside `_ensure_signal_coverage`.

---

## Phase 0 — Lock back-compat (SDK, DO FIRST) — FR-0, FR-11

- Add `tests/unit/observability/test_http_golden.py` with a **fixture matrix** (CRP R1-S3), not one service: (a) `http_server` **with `availability` set** (gates the FR-13a gauge carve-out), (b) **counter-only** http service with no duration histogram (gates the FR-12a AND-composition), (c) a `grpc_server`. Assert full-YAML equality per fixture against committed goldens.
- This is the regression gate for every later phase. No generator code changes yet.

## Phase 1 — Cross-repo prerequisites (ContextCore / cap-dev-pipe) — CR-1, CR-2, CR-3

*Lands in the producer repo, not here. Sequenced first because §3 consumes it, but the SDK degrades gracefully (FR-11) so Phases 2–3 can proceed against fixtures before Phase 1 ships.*
- CR-1/CR-2: add `spec.requirements.functional[]` + `traceability[]` to the manifest schema; populate `traceability[]` by forwarding `ingestion-traceability.json` `requirement_mappings[]` (`plan_ingestion_workflow.py:2207`). Author `signal_kind`/`target` (see OQ-7).
- CR-3: add `instrumentation_hints[svc].kind` to the Stage-4 EXPORT producer.
- Deliverable back to SDK: updated sample fixtures (onboarding-metadata.json with `kind`; `.contextcore.yaml` with `functional[]`).

## Phase 2 — SDK consumption + determination — FR-4/5/6/7/12/13/14

> **Build order (CRP R1-S4):** the resolver (FR-12) calls into the kind→profile table (FR-6) and per-signal_kind thresholds (FR-7), so those must exist first. Split into **2a (tables + admission)** → **2b (resolver + gate + RED deletion)**.

**Phase 2a — models, admission, tables (no determination change yet)**
- **Models** (`artifact_generator_models.py`): `kind` on `ServiceHints` modeled as **one-or-more** (FR-12b) and `transport` made **optional** (FR-14); add a `FunctionalRequirement` dataclass + `functional_requirements` to `BusinessContext`.
- **Admission (FR-14, CRP R1-S1)** (`artifact_generator_context.py:298`): **relax the transport hard-drop** — admit a hint that declares a `kind` even with no transport (do not `continue`). *Load-bearing: without this the FR-12c ∅-path and FR-9 report are dead code.* Also read `hint.get("kind")` (~:327) and `requirements.get("functional")`/`traceability` (~:390); absent ⇒ empty ⇒ today's path.
- **FR-6 — kind→profile table** (`metric_descriptor.py`): add `async_worker`/`batch`/`cron`/`stream` rows to `_PROFILES` + a `kind→profile` map beside `_TRANSPORT_DEFAULTS` + a `kind` tier in `resolve_descriptor` (kind wins; HTTP fallback for the request family only).
- **FR-7 — per-signal_kind thresholds** (`artifact_generator_generators.py:40`): `_DEFAULT_THRESHOLDS` keyed by `signal_kind` (distinct units for `lag` vs `freshness`, per FR-5 glosses); selected in `_resolve_threshold` (~:127).

**Phase 2b — determination (resolver, gate, RED deletion)**
- **FR-12 — SLI-kind resolver.** Add `resolve_sli_kinds(kind, functional[], transport) → Set[SignalKind]` beside the descriptor (`artifact_generator.py:519`); **unions** per-kind default sets for hybrids (FR-12b). Request-serving + no declaration ⇒ `{latency,availability,throughput}`; non-request + no declaration ⇒ `∅`.
- **FR-12a — gate = AND, not replace (CRP R1-S5).** Each alert/SLO block emits iff *(SLI kind ∈ resolved set)* **AND** *(its source metric is present)* — the SLI-kind gate wraps, never replaces, the existing `type=="histogram" and "duration" in name` guard (`generators.py:218/934`). The `latency`/`availability` rows *are* today's code, extracted not rewritten.
- **FR-13 — delete unconditional RED** (`artifact_generator_generators.py:795`): rewrite `_ensure_red_coverage` → `_ensure_signal_coverage(panels, sli_kinds, …)`; backfill only what the set implies; no-op otherwise. **FR-13a (CRP R1-S2):** re-emit the **Availability (1h) gauge** (`generators.py:876`) iff `availability ∈ sli_kinds` AND `business.availability` set — it is availability-kind, not RED-completion. **FR-13b (CRP R1-S8):** reuse the exact `has_rate`/`has_error` detectors (`generators.py:820` fallback), don't re-derive presence.
- **FR-5 — signal-kind derivation rows**: `queue_depth`/`retry_rate`/`freshness`/`run_success`/`lag`/`saturation` templates, additive; a kind may suppress a default SLI (worker suppresses latency).

## Phase 3 — Traceability + coverage — FR-8, FR-9

- **FR-8**: at FR-driven emit sites, attach a `DerivationTrace` carrying the source FR id (or add `source_fr` to `ArtifactResult`); it flows into `observability-manifest.yaml` `derivation_rules` (`artifact_generator.py:1150`) with no extra plumbing.
- **FR-9**: add an `fr_coverage` block to the `_write_index` summary (`artifact_generator.py:1077`), distinguishing **two gap classes (CRP R1-S7)**: `resolved=∅` (no kind) and `resolved≠∅, produced=0` (declared signal_kind, metric absent — the pilot's real symptom). Mirrors `_record_unimplemented_artifact_types` (:870).

## Phase 4 — Doc supersession — FR-10

- Update `docs/design/UNIFIED_OBSERVABILITY_MANIFEST_REQUIREMENTS.md` (or add `docs/design/observability-requirement-shaped/ADR-001-per-fr-derivation.md`) reversing the "new manifest schema" / "per-FR derivation" non-goals, citing this requirements doc.

---

## Cross-repo vs SDK-only

| FR | Owner |
|----|-------|
| CR-1, CR-2, CR-3 (schema + export + `signal_kind`/`kind` authoring) | **Cross-repo** (ContextCore / cap-dev-pipe) |
| FR-0, FR-4 (consume), FR-5, FR-6, FR-7, FR-8, FR-9, FR-10, FR-11, **FR-14 (relax transport-drop SDK-side)** | **SDK** (this repo) |

## Validation

- Phase 0 golden **matrix** (availability-set / counter-only / grpc) stays green through Phases 2–3 (FR-11 parity).
- New unit tests: `async_worker` descriptor resolution; worker gets no `http_server_duration` SLO; **transport-less `kind=async_worker` hint becomes a ServiceHints and reaches the resolver** (CRP R1-S1); **counter-only http service resolving to the full triplet emits no latency block** (CRP R1-S5 AND-gate); `signal_kind`-keyed derivation emits queue/retry/freshness artifacts; `fr_coverage` shows **both** a `resolved=∅` service and a `resolved≠∅, produced=0` FR (CRP R1-S7).
- **Hybrid test (CRP R1-S6):** a service whose `kind` implies http+worker emits both a latency SLO (http) and a queue_depth artifact (worker), with no `http_server_duration` SLO on the worker series.
- **Suppression test (CRP R1-S9):** a worker `kind` fed a stray `http_server_duration` convention metric upstream still emits no latency SLO (kind suppresses) — covers §0.3's second failure source, which FR-13 alone does not.
- End-to-end (OQ-5): once CR-3 emits `kind`, run a minimal worker+FR pilot; confirm the 6-of-7-missing gap closes.

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
| R1-S1 | Relax transport-drop SDK-side in Phase 2 | CRP R1 (opus-4-8) | Applied to **Phase 2a** admission step (+ REQUIREMENTS FR-14). | 2026-07-22 |
| R1-S2 | Availability-gauge carve-out in FR-13 | CRP R1 | Applied to **Phase 2b** FR-13a. | 2026-07-22 |
| R1-S3 | Phase 0 golden fixture matrix | CRP R1 | Applied to **Phase 0** (availability-set / counter-only / grpc). | 2026-07-22 |
| R1-S4 | Sequence FR-6/7 before the resolver | CRP R1 | Applied — Phase 2 split into **2a (tables) → 2b (resolver)**. | 2026-07-22 |
| R1-S5 | AND-gate composition | CRP R1 | Applied to **Phase 2b** FR-12a. | 2026-07-22 |
| R1-S6 | Hybrid-service test | CRP R1 | Applied to **Validation**. | 2026-07-22 |
| R1-S7 | Two coverage-gap classes | CRP R1 | Applied to **Phase 3** FR-9. | 2026-07-22 |
| R1-S8 | Reuse presence detectors verbatim | CRP R1 | Applied to **Phase 2b** FR-13b. | 2026-07-22 |
| R1-S9 | Worker-fed-http-metrics suppression test | CRP R1 | Applied to **Validation**. | 2026-07-22 |

*All 9 R1 S-suggestions ACCEPTED + applied. No rejections. Two load-bearing claims (transport hard-drop, availability-gauge independence) byte-verified against source first.*

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8 — 2026-07-22

- **Reviewer**: claude-opus-4-8
- **Date**: 2026-07-22 00:00:00 UTC
- **Scope**: v0.4 seam soundness — Phase 2 (FR-12/13 resolver + gate + RED deletion), sequencing, and validation. Code-grounded against `artifact_generator.py:519/528`, `artifact_generator_generators.py:40/478/795`, `artifact_generator_context.py:298`.

**Executive summary (top risks / gaps):**

- Phase 2 lists reading `hint.get("kind")` at context `~:327` but **does not** touch the transport hard-drop at `:298–301`; a transport-less worker is `continue`d before the resolver ever runs, so FR-9's ∅-report and FR-12's ∅-path are unreachable SDK-side (blocking gap; the plan leaves this to a producer *SHOULD*).
- The FR-13 rewrite must special-case the **Availability (1h) gauge** (`generators.py:876`), which is availability-kind, not RED — the plan's one-line "backfill only what the set implies" hides it.
- Phase 0 golden fixture is a single `http_server`; parity soundness needs it to also cover an availability-set service, a counter-only service, and (once CR-3 lands) a worker — else Phases 2–3 can pass green while breaking off-template output.
- The plan does not state the **gate composition** (SLI-kind gate ANDed with existing metric-presence gates); if inverted it silently changes plain-http output.
- Phase 2 orders FR-12/FR-13 before FR-6/FR-7, but the resolver's per-kind default sets (FR-12) depend on the kind→profile table (FR-6) and the per-kind thresholds (FR-7) existing — an ordering hazard.
- No test named for the **hybrid** (http+worker) service; the Validation section enumerates only pure `async_worker`.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Architecture | high | Add an explicit Phase 2 step to make `transport` optional and **relax the transport-required drop** (`artifact_generator_context.py:298`) SDK-side when a `kind` is present — do not defer it to CR-3's producer *SHOULD*. | The plan reads `hint.get("kind")` at `~:327` but the `continue` at `:298` fires first, dropping the service before the resolver runs; FR-9/FR-12 ∅-paths are then dead code. Load-bearing and currently unowned in the SDK phase. | Phase 2 (new bullet before FR-12 resolver) | Unit test: hint with `kind=async_worker` + no `transport` produces a ServiceHints and reaches the resolver. |
| R1-S2 | Risks | high | In the FR-13 bullet, name the **Availability (1h) gauge** (`generators.py:876–905`) as a separately-preserved `availability`-kind artifact; `_ensure_signal_coverage` must re-emit it iff `availability ∈ sli_kinds` AND `business.availability` set. | The plan's "backfill only what the set implies; no-op otherwise" omits that the gauge fires on `business.availability` alone, bypassing the `has_rate and has_error` guard — a naive deletion regresses every http fixture with an availability SLO. | Phase 2, FR-13 bullet | Golden fixture with `availability` set; assert gauge present and byte-identical after the rewrite. |
| R1-S3 | Validation | high | Expand the Phase 0 golden beyond "one representative http_server" to a **fixture matrix**: (a) http_server with `availability` set, (b) counter-only http service (no duration histogram), (c) a grpc_server. Each is the regression gate for a distinct parity risk. | A single fixture that happens to carry a duration histogram + availability masks the two composition risks (R1-S2, and the AND-gate in R1-S5). "Stays green through Phases 2–3" is only meaningful if the fixture exercises the paths those phases change. | Phase 0 | Assert full-YAML equality per fixture against committed goldens; CI gate. |
| R1-S4 | Ops | medium | Sequence FR-6 (kind→profile table) and FR-7 (per-signal_kind thresholds) **before** the FR-12 resolver within Phase 2, or split Phase 2 into 2a (tables) → 2b (resolver+gate+FR-13). | `resolve_sli_kinds` returns `kind`-implied default sets and each SLI needs a profile row + a threshold; building the resolver first leaves it calling into not-yet-existing tables. The current bullet order (FR-4→5→6→7→12→13→5) is not a valid build order. | Phase 2 (reorder / sub-phase) | Each sub-phase's unit tests pass independently; resolver test depends only on merged table PRs. |
| R1-S5 | Interfaces | high | State in Phase 2 that the per-SLI-kind emit gate is **ANDed** with the existing per-metric gate (`type=="histogram" and "duration" in name`, `generators.py:218/934`), mirroring how `_EXTENDED_PER_SERVICE_GENERATORS` is gated at `:556` — not a replacement of the per-metric loop. | The seam note says "gate the triplet … mirrors the extended-generator gate at :556," but the extended gate is *presence-of-declared-type*; the triplet's real guard is *presence-of-metric*. Conflating them risks emitting a latency block for a service that resolves to `{latency}` but has no duration histogram. | Phase 2, FR-12 "gate the triplet" bullet | Fixture resolving to full triplet with counter-only metrics; assert no latency alert/SLO emitted (byte-identical to today). |
| R1-S6 | Validation | medium | Add a hybrid-service test to the Validation section: a service whose `kind` implies http+worker emits both a latency SLO (http) and a queue_depth artifact (worker), with no `http_server_duration` SLO on the worker series. | Validation currently lists only pure `async_worker`. The kind→profile table + scalar `kind` leave hybrids ambiguous (see REQUIREMENTS R1-F5); without a test the union semantics ship unspecified. | Validation (new bullet) | The hybrid fixture emits the union of both profiles' SLIs; assert no cross-series SLO. |
| R1-S7 | Ops | low | Have Phase 3 FR-9 distinguish two coverage-gap classes in the `fr_coverage` block: `resolved=∅` (no kind) vs `resolved≠∅, produced=0` (declared signal_kind, metric absent). | The pilot's "6 of 7 FRs → nothing" is the *unfulfilled* class; a report that only lists ∅ services still masks it. Both mirror `_record_unimplemented_artifact_types` but are semantically distinct. | Phase 3, FR-9 bullet | `fr_coverage` fixture with one ∅ service and one unfulfilled FR; assert both classes appear distinctly. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S8 | Risks | medium | The FR-13 rewrite must reuse `has_rate_panel`/`has_error_panel` (`observability_artifact_checks.py:1167/1175`) verbatim for presence detection, not re-derive it. Note this in the Phase 2 FR-13 bullet. | `_ensure_red_coverage` today falls back to a fuzzy inline heuristic (`generators.py:820`); a re-implementation that computes "what the set implies" differently can add/drop a panel on an http fixture that currently trips the heuristic, breaking FR-11 byte-identity. | Phase 2, FR-13 bullet | Golden fixture whose panels already satisfy RED heuristically; assert zero panels added post-rewrite. |
| R1-S9 | Validation | low | Add a validation step asserting the descriptor for a non-request `kind` yields a **non-http throughput/latency series**, so a worker never receives `http_server_duration` even if some upstream fed it http convention metrics (the §0.3 "worker fed http metrics upstream" path). | §0.3 flags two failure sources: unconditional synthesis (fixed by FR-13) *and* the worker being fed http convention metrics upstream. FR-13 alone does not cover the second; the per-metric loop still emits on whatever metrics are present. | Validation | Fixture: worker `kind` + stray `http_server_duration` convention metric; assert no latency SLO on it (kind suppresses). |

---

## Requirements Coverage Matrix — R1

Analysis only (coverage of REQUIREMENTS.md FR/CR IDs by PLAN.md phases). Not triage.

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-0 (golden regression test first) | Phase 0 | Partial | Single http_server fixture; missing availability-set / counter-only / grpc variants (R1-S3). |
| CR-1 (manifest functional[]) | Phase 1 | Full | Cross-repo; OQ-7 authoring open but non-blocking. |
| CR-2 (manifest traceability[]) | Phase 1 | Full | Cross-repo forward of `requirement_mappings[]`. |
| CR-3 (onboarding kind + relax transport drop) | Phase 1 | Partial | Transport-drop relaxation is a producer *SHOULD*; the SDK-side `:298` drop is not planned (R1-S1, R1-F6). |
| FR-12 (contract-first SLI-kind determination) | Phase 2 (resolver + gate) | Partial | Gate-composition (AND vs replace) unstated (R1-S5); ∅-path unreachable while `:298` drops workers (R1-S1); hybrid union unspecified (R1-S6). |
| FR-13 (delete unconditional RED synthesis) | Phase 2 | Partial | Availability-gauge carve-out unnamed (R1-S2); presence-detection reuse unnamed (R1-S8). |
| FR-4 (partial-forward, don't re-author) | Phase 2 (context reads) | Full | — |
| FR-5 (signal_kind primary axis + enum) | Phase 2 (derivation rows) | Partial | `retry_rate`/`run_success` overlap + `lag`/`freshness` discriminator unresolved (R1-F3, R1-F4). |
| FR-6 (kind→profile table) | Phase 2 (`_PROFILES` rows + map + tier) | Partial | Ordering: table must precede resolver (R1-S4); hybrid row absent (R1-F5). |
| FR-7 (per-signal_kind thresholds) | Phase 2 (`_DEFAULT_THRESHOLDS` keyed) | Partial | Per-kind units for lag vs freshness undefined (R1-F4); build-order dependency (R1-S4). |
| FR-8 (stamp originating FR id) | Phase 3 (DerivationTrace / source_fr) | Full | Attaches to existing channel. |
| FR-9 (FR + SLI-kind + ∅ coverage report) | Phase 3 (`fr_coverage` in `_write_index`) | Partial | Does not distinguish resolved=∅ vs resolved≠∅/produced=0 (R1-S7, R1-F9); depends on `:298` fix (R1-S1). |
| FR-10 (supersede design doc) | Phase 4 | Full | — |
| FR-11 (absent-input byte-identical parity) | Phase 0 + Validation | Partial | Parity only as strong as the golden matrix (R1-S3); heuristic RED-detection reuse unstated (R1-S8). |
| NR-1..NR-5 | (constraints) | Full | Honored; NR-3 "ship the table" matches Phase 2 FR-6. |
| OQ-5 (pilot grounding) | Validation (E2E) | Partial | Correctly non-blocking; deferred to post-CR-3 pilot. |
| OQ-7 (who authors signal_kind/target) | Phase 1 note | Partial | Non-blocking for SDK seam but gates CR-1 scope; flagged, not resolved. |
