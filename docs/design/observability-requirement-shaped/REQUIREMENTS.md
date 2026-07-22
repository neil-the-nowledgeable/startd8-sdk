# Requirement-Shaped, Service-Kind-Aware Observability Generation — Requirements

**Version:** 0.3.1 (Post design-principle hardening — ready for CRP)
**Date:** 2026-07-22
**Status:** Ready for review
**Issue:** #226
**Supersedes (in part):** `docs/design/UNIFIED_OBSERVABILITY_MANIFEST_REQUIREMENTS.md` non-goals "New manifest schema" and per-FR derivation (user decision, 2026-07-22: reverse those — see FR-10).

---

## 0. Planning Insights (Self-Reflective Update)

> Documents what changed between v0.1 (pre-planning) and v0.2. The planning pass
> (mapping every FR to real code) produced **8 material corrections** — well over the
> 30% threshold, i.e. the draft was premature and the loop paid for itself.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| FR-1/2/3 add fields "to the manifest / onboarding-metadata" as if the SDK owns those schemas | The SDK **only consumes** `onboarding-metadata.json` (`load_onboarding_metadata`) and `.contextcore.yaml` (`load_business_context`, `artifact_generator_context.py:349`). The producer is ContextCore / cap-dev-pipe Stage-4 EXPORT. | FR-1/2/3 are **cross-repo prerequisites**, not SDK deliverables. Reclassified as CR-* (§2). SDK work = *consumption only*. |
| FR-4 "forward FRs from plan-ingestion" — feasibility unknown (OQ-2) | Plan-ingestion **already emits** `ingestion-traceability.json` via `_build_traceability_artifact` (`plan_ingestion_workflow.py:2207`), with `requirement_mappings[]` carrying `requirement_id`, `feature_ids`, `task_ids`, `acceptance_obligations`, `source_references`. But it has **no `signal_kind`, no numeric target, no service binding**. | FR-4 is **partial-forward**: FR ids + traceability are forwardable cheaply; `signal_kind`/`target`/`service` must be *authored* (they don't exist upstream yet). Split accordingly. |
| FR-6 "branch metric template on service kind" implies scattered if-kind logic | `MetricDescriptor` + named `_PROFILES` (`metric_descriptor.py:127`) **is already the per-shape strategy seam** — resolved once per service (`resolve_descriptor`, `artifact_generator.py:519`) and threaded into every descriptor-aware generator. | FR-6/FR-7 **collapse into** adding an `async_worker` profile + a kind→profile map. Far smaller and more maintainable than a new branch mechanism. |
| FR-7 "replace the single `_DEFAULT_THRESHOLDS`" | `_DEFAULT_THRESHOLDS` (`artifact_generator_generators.py:40`) is **already overridable** per-run via `business.default_thresholds` (`_resolve_threshold`, `:127`). | FR-7 becomes "make `default_thresholds` **kind-keyed**" — plumbing exists; only the shape (flat→per-kind) + lookup change. |
| "Workers get `http_server_duration` SLOs they can't satisfy" is a main-loop bug | The alert/SLO loops gate strictly on `type=="histogram" and "duration" in name` (`generators.py:218/934`). A worker carrying no duration metric already emits nothing there. The spurious RED most likely comes from `_ensure_red_coverage` (`generators.py:795`), which **unconditionally synthesizes** request-rate/availability panels, or from the worker being *fed* http convention metrics upstream. | FR-6's real SDK fix = make **`_ensure_red_coverage` kind-aware** (the one legitimate `if kind` branch). Root cause re-scoped. |
| NR-4 back-compat is protected by golden tests | `test_parity.py` checks metric-name export parity, not full output. **No full-YAML golden/snapshot test of http_server artifacts exists.** | Added **FR-0**: land a golden test locking today's http output *before* touching generators. Back-compat holds structurally (absent kind ⇒ transport default ⇒ identical descriptor) but needs a regression gate. |
| FR-8/FR-9 need new plumbing | `DerivationTrace` + `ArtifactResult.derivations` (surfaced as `derivation_rules` in the manifest) and `GenerationReport` coverage summaries + `_record_unimplemented_artifact_types` (`:870`) are existing patterns. | FR-8/FR-9 attach to existing channels — low churn, no new subsystem. |
| FR-3 "kind could be inferred SDK-side like `detected_databases`" (OQ-3) | `detected_databases` is **not** inferred SDK-side — it arrives pre-computed in the onboarding hint (`artifact_generator_context.py:332`). No SDK-side queue/worker detection exists to reuse. | Kind is **producer-supplied** (cross-repo). SDK may only add a deterministic *fallback* (`transport=http ⇒ http_server`). |

**Resolved open questions:**
- **OQ-1 → onboarding-metadata.json is produced by ContextCore / cap-dev-pipe Stage-4 EXPORT, not the SDK.** SDK consumes it. FR-3/FR-4 forwarding is producer-side.
- **OQ-2 → YES, a structured FR/traceability artifact already exists** (`ingestion-traceability.json`), but lacks `signal_kind`/`target`/`service`. Forward is partial (see FR-4).
- **OQ-3 → kind is producer-supplied** (like `detected_databases`); SDK adds only a transport→kind fallback.
- **OQ-4 → worker metric names live in the new `async_worker` MetricDescriptor profile**; custom signals are declared per-FR via `signal_kind`+`target`.
- **OQ-5 → pilot artifact still not located.** Root-cause hypothesis refined to `_ensure_red_coverage`. Recommend a fresh minimal worker+FR pilot to ground thresholds once the producer emits `kind` (tracked as a validation task, not a blocker for the SDK-side spec).
- **OQ-6 → additive by default.** FR-driven signals are additive to the convention triplet; a kind may *suppress* the default availability/latency SLO (workers suppress latency).

### 0.1 Lessons-Learned Hardening (v0.3)

> Applied the SDK **Design-Docs** lessons (Leg 6) before CRP. Each changed the draft:

- **[Phantom-requirement pruning]** — FR-1/2/3 describe schema fields owned by *other repos*; presenting them as SDK FRs would over-claim scope → moved to **§2 Cross-Repo Prerequisites (CR-1..CR-3)**, leaving §3 as the SDK-owned deliverables only.
- **[Phantom-reference audit]** — every code symbol this spec names was grep-verified to exist → added **§5 Reference Audit** (all PRESENT: `_PROFILES`, `resolve_descriptor`, `_ensure_red_coverage`, `_DEFAULT_THRESHOLDS`, `_resolve_threshold`, `_build_traceability_artifact`, `DerivationTrace`, `_record_unimplemented_artifact_types`).
- **[Extend-vs-build-separate (abstraction invariants)]** — the draft's "branch metric template" risked a parallel mechanism beside the existing profile seam → FR-6/FR-7 rewritten to **extend `MetricDescriptor._PROFILES`**, not build a new kind-dispatcher.
- **[Vocabulary-drift single-source ownership]** — the `signal_kind` enum (availability|latency|queue_depth|retry_rate|freshness|throughput|custom) could drift across the manifest schema and the generator → **this doc is its normative owner** (§3, FR-5); CR-1 and the generator cite it, not restate it.

### 0.2 Design-Principle Hardening (v0.3.1)

> Checked against `docs/design-princples/`. Each changed the draft:

- **[Mottainai]** — don't re-author what an earlier stage produced → FR-4 mandates *forwarding* `ingestion-traceability.json`'s `requirement_mappings[]` rather than re-parsing requirements; only the genuinely-absent `signal_kind`/`target` are authored.
- **[Genchi Genbutsu]** — bind to the real authoritative artifact and respect the boundary → FRs bind to the plan's *actual* FR ids (not a template), and the SDK **stays consume-only** on upstream schemas (CR-* own the writes). No SDK injection into producer artifacts.
- **[Accidental-Complexity anti-principle]** — prefer one general rule to an enumerated special-case list → the profile-extension seam (one rule: kind→descriptor) replaces per-generator `if kind==...` branches; the *sole* justified branch is `_ensure_red_coverage` (RED is a server semantic, not a metric-name swap).
- **[Context-Correctness-by-Construction]** — required context must be declared+validated+degradable, never a silent `None` → **FR-11**: every new field (`kind`, `functional[]`) is optional and its absence yields *byte-identical* pre-#226 output (the NR-4 guarantee, made constructive and test-gated by FR-0).
- **[Hitsuzen]** — derive the determinable deterministically → kind fallback (`transport→kind`) and `signal_kind→metric series` mapping are deterministic table lookups, not LLM calls.

---

## 1. Problem Statement

The observability artifact generator derives a **generic per-service HTTP template** and ignores (a) the plan's functional requirements + traceability and (b) each service's *kind*. Surfaced by the Mastodon status-fanout pilot.

**Behavior today (source-grounded):** iterates `service.convention_metrics`; emits only availability + latency-p99 SLOs on `http_server_duration`; hardcoded defaults `availability="99"`/`latency_p99="500ms"` (`artifact_generator_generators.py:40`); branches only on `transport` (http/grpc), never on service kind.

**Consequences (pilot; re-verify per OQ-5):** every service gets the same two SLOs; an async Sidekiq worker (`mastodonsidekiq`, no HTTP) got `http_server_duration` SLOs; FR-specific signals (queue depth, retry rate, fan-out freshness) produced **zero** artifacts — 6 of 7 FRs yielded nothing.

---

## 2. Cross-Repo Prerequisites (owned by ContextCore / cap-dev-pipe — NOT this repo)

> These unblock the SDK work but land in the producer. Tracked here as dependencies with acceptance criteria; the SDK consumes them (§3) and degrades gracefully until they arrive (FR-11).

- **CR-1 — Manifest carries functional requirements.** `.contextcore.yaml` `spec.requirements.functional[]`, each: `id`, `description`, `signal_kind` (enum owned by §3/FR-5), optional `target`/threshold, optional `service` binding.
- **CR-2 — Manifest carries traceability.** `spec.requirements.traceability[]` mapping FR id → service(s); SHOULD be populated by forwarding `ingestion-traceability.json` `requirement_mappings[]` (Mottainai).
- **CR-3 — Onboarding metadata carries service kind.** `instrumentation_hints[svc].kind ∈ {http_server, grpc_server, async_worker, unknown}`, producer-supplied (inferred where possible, e.g. queue/worker library detection, the same mechanism that supplies `detected_databases`).

## 3. Requirements (SDK — this repo)

### Back-compat gate
- **FR-0 — Golden regression test first.** Before any generator change, add a full-YAML golden/snapshot test for a representative `http_server` service (alert + SLO + dashboard_spec) under `tests/unit/observability/`. Every later FR runs against it. (None exists today.)

### Consume + derive
- **FR-4 — Partial-forward, don't re-author.** Consume forwarded FR ids + traceability (CR-2). Only the genuinely-absent `signal_kind`/`target`/`service` are authored/declared; the ids, feature/task mappings, and source references come from `ingestion-traceability.json` unchanged.
- **FR-5 — Consume functional requirements → derive signal-kind SLO/alert kinds.** Read `spec.requirements.functional[]`; for each FR, derive artifacts keyed on `signal_kind`. **Normative `signal_kind` enum (owned here):** `availability`, `latency`, `queue_depth`, `retry_rate`, `freshness`, `throughput`, `custom`. At minimum `queue_depth`, `retry_rate`, `freshness` gain derivation paths beyond today's availability+latency. Additive by default (OQ-6).
- **FR-6 — Kind-aware derivation via profile extension.** Add an `async_worker` `MetricDescriptor` profile (`metric_descriptor.py:_PROFILES`) with worker series (queue-latency/job-duration/retry-failure), and a `kind→profile` default map beside `_TRANSPORT_DEFAULTS`; thread `kind` into `resolve_descriptor` so kind wins over transport when present. Make **`_ensure_red_coverage` kind-aware** so it does not synthesize HTTP RED for a worker. No worker shall receive an `http_server_duration` SLO.
- **FR-7 — Per-kind default thresholds.** Make `default_thresholds` / `_DEFAULT_THRESHOLDS` **kind-keyed** (a worker's defaults are queue/retry-oriented, not `latency_p99="500ms"`); select the kind's block in `_resolve_threshold`.

### Traceability + visibility
- **FR-8 — Stamp originating FR id on outputs.** Each FR-derived SLO/alert records its source FR id via a `DerivationTrace` (or a `source_fr` field on `ArtifactResult`), surfaced in `observability-manifest.yaml`.
- **FR-9 — FR coverage report.** The generation report SHALL list which FRs produced artifacts and which produced **none** (the pilot's exact gap), mirroring `_record_unimplemented_artifact_types`. Makes "6 of 7 missing" visible without a manual grep.

### Invariants + docs
- **FR-11 — Absent-input parity (constructive).** With no `functional[]` and no `kind`, output is **byte-identical** to pre-#226 for every service (gated by FR-0). New fields are optional; absence degrades to today's convention path.
- **FR-10 — Supersede the design doc.** Update `UNIFIED_OBSERVABILITY_MANIFEST_REQUIREMENTS.md` (or add an ADR) recording that per-FR derivation + the manifest-schema extension are now in-scope, reversing the prior non-goals.

---

## 4. Non-Requirements

- **NR-1 — No target-project code introspection.** Derive from declared FRs + convention metrics only (the prior doc's rejection stands).
- **NR-2 — No new telemetry runtime.** Changes *what artifacts are derived*, not how the target app is instrumented.
- **NR-3 — No exhaustive kind taxonomy.** Ship http_server/grpc_server/async_worker/unknown; defer batch/cron/stream.
- **NR-4 — No breaking change to today's HTTP output** (now the constructive FR-11 + FR-0 gate).
- **NR-5 — SDK does not write upstream schemas.** CR-1..CR-3 land in the producer; the SDK only consumes (Genchi Genbutsu boundary).

## 5. Reference Audit

All symbols this spec names were grep-verified PRESENT:

| Symbol | File | Used by |
|--------|------|---------|
| `_PROFILES`, `resolve_descriptor`, `_TRANSPORT_DEFAULTS` | `metric_descriptor.py` | FR-6 |
| `_DEFAULT_THRESHOLDS`, `_resolve_threshold`, `_ensure_red_coverage` | `artifact_generator_generators.py` | FR-6, FR-7 |
| `extract_service_hints`, `load_business_context` | `artifact_generator_context.py` | FR-4, FR-6 (consumption) |
| `ServiceHints`, `BusinessContext`, `DerivationTrace`, `ArtifactResult`, `GenerationReport` | `artifact_generator_models.py` | FR-5, FR-8, FR-9 |
| `_record_unimplemented_artifact_types`, `_write_index` | `artifact_generator.py` | FR-9 |
| `_build_traceability_artifact`, `ingestion-traceability.json`, `requirement_mappings[]` | `plan_ingestion_workflow.py:2207` | FR-4 (forward source) |

## 6. Remaining Open Questions

- **OQ-5 (validation)** — locate/read the Mastodon `coverage-gap-analysis.md`, or run a fresh minimal worker+FR pilot to ground `async_worker` metric names + thresholds once CR-3 emits `kind`. Non-blocking for the SDK spec.
- **OQ-7 (new)** — who authors `signal_kind`/`target` for each FR (CR-1): the plan author by hand, a plan-ingestion enrichment pass, or an LLM classifier over `requirements_hints[]`? Determines whether CR-1 is pure schema or schema + an authoring step.

---

*v0.3.1 — Post design-principle hardening. 8 planning corrections; 3 FRs reclassified cross-repo (CR-1..3); FR-6/7 collapsed to profile extension; FR-0 (golden gate) and FR-11 (constructive parity) added; 5 OQs resolved. Applied lessons: phantom-requirement-pruning, phantom-reference-audit, extend-vs-build-separate, vocabulary-single-source. Applied principles: Mottainai, Genchi Genbutsu, Accidental-Complexity, Context-Correctness-by-Construction, Hitsuzen. Ready for CRP.*
