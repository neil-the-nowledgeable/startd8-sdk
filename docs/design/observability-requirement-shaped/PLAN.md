# Implementation Plan — Requirement-Shaped, Service-Kind-Aware Observability (#226)

**Version:** 1.0 (matches REQUIREMENTS v0.3.1)
**Date:** 2026-07-22
**Companion:** `REQUIREMENTS.md`

> Seam decision (from planning): **extend the existing `MetricDescriptor` profile
> strategy**, do not build a parallel kind-dispatcher. The one legitimate `if kind`
> branch is `_ensure_red_coverage` (RED is a server semantic). Everything else is a
> table lookup (kind→profile, kind→thresholds, signal_kind→series).

---

## Phase 0 — Lock back-compat (SDK, DO FIRST) — FR-0, FR-11

- Add `tests/unit/observability/test_http_golden.py`: generate alert + SLO + dashboard_spec for one representative `http_server` service from a fixed onboarding-metadata + `.contextcore.yaml` fixture; assert full-YAML equality against a committed golden.
- This is the regression gate for every later phase. No generator code changes yet.

## Phase 1 — Cross-repo prerequisites (ContextCore / cap-dev-pipe) — CR-1, CR-2, CR-3

*Lands in the producer repo, not here. Sequenced first because §3 consumes it, but the SDK degrades gracefully (FR-11) so Phases 2–3 can proceed against fixtures before Phase 1 ships.*
- CR-1/CR-2: add `spec.requirements.functional[]` + `traceability[]` to the manifest schema; populate `traceability[]` by forwarding `ingestion-traceability.json` `requirement_mappings[]` (`plan_ingestion_workflow.py:2207`). Author `signal_kind`/`target` (see OQ-7).
- CR-3: add `instrumentation_hints[svc].kind` to the Stage-4 EXPORT producer.
- Deliverable back to SDK: updated sample fixtures (onboarding-metadata.json with `kind`; `.contextcore.yaml` with `functional[]`).

## Phase 2 — SDK consumption + derivation — FR-4, FR-5, FR-6, FR-7

- **Models** (`artifact_generator_models.py`): add `kind: str = ""` to `ServiceHints`; add a `FunctionalRequirement` dataclass and `functional_requirements: List[FunctionalRequirement]` to `BusinessContext`.
- **Context** (`artifact_generator_context.py`): read `hint.get("kind")` in `extract_service_hints` (~:327); read `requirements.get("functional")`/`traceability` in `load_business_context` (~:390). Absent ⇒ empty ⇒ today's path (FR-11).
- **Descriptor** (`metric_descriptor.py`): add `async_worker` to `_PROFILES` (queue-latency histogram, job-duration bucket, retry/failure counter, job-failure `error_selector`); add `kind→profile` map beside `_TRANSPORT_DEFAULTS`; add a `kind` tier to `resolve_descriptor` (kind wins over transport). Wire `kind` at the resolution call site (`artifact_generator.py:519`).
- **Thresholds** (`artifact_generator_generators.py`): make `_DEFAULT_THRESHOLDS` kind-keyed; select the kind block in `_resolve_threshold` (~:127).
- **RED** (`artifact_generator_generators.py:795`): gate `_ensure_red_coverage` synthesis on kind (skip HTTP RED for `async_worker`). — the single justified `if kind` branch.
- **FR-driven pass** (`artifact_generator_generators.py`): new derivation keyed on each FR's `signal_kind` (`queue_depth`/`retry_rate`/`freshness`), additive to the convention triplet.

## Phase 3 — Traceability + coverage — FR-8, FR-9

- **FR-8**: at FR-driven emit sites, attach a `DerivationTrace` carrying the source FR id (or add `source_fr` to `ArtifactResult`); it flows into `observability-manifest.yaml` `derivation_rules` (`artifact_generator.py:1150`) with no extra plumbing.
- **FR-9**: add an `fr_coverage` block to the `_write_index` summary (`artifact_generator.py:1077`) — FRs with zero produced artifacts listed explicitly, mirroring `_record_unimplemented_artifact_types` (:870).

## Phase 4 — Doc supersession — FR-10

- Update `docs/design/UNIFIED_OBSERVABILITY_MANIFEST_REQUIREMENTS.md` (or add `docs/design/observability-requirement-shaped/ADR-001-per-fr-derivation.md`) reversing the "new manifest schema" / "per-FR derivation" non-goals, citing this requirements doc.

---

## Cross-repo vs SDK-only

| FR | Owner |
|----|-------|
| CR-1, CR-2, CR-3 (schema + export + `signal_kind`/`kind` authoring) | **Cross-repo** (ContextCore / cap-dev-pipe) |
| FR-0, FR-4 (consume), FR-5, FR-6, FR-7, FR-8, FR-9, FR-10, FR-11 | **SDK** (this repo) |

## Validation

- Phase 0 golden test stays green through Phases 2–3 (FR-11 parity).
- New unit tests: `async_worker` descriptor resolution; worker gets no `http_server_duration` SLO; `signal_kind`-keyed derivation emits queue/retry/freshness artifacts; `fr_coverage` lists a 0-artifact FR.
- End-to-end (OQ-5): once CR-3 emits `kind`, run a minimal worker+FR pilot; confirm the 6-of-7-missing gap closes.
