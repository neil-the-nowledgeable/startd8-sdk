# Requirement-Shaped, Service-Kind-Aware Observability Generation — Requirements

**Version:** 0.6 (Post Phase-2a start — FR-14 shipped, FR-7 reconciled with #234; see §0.4)
**Date:** 2026-07-22
**Status:** Ready for implementation
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

### 0.3 De-Overfit Generalization (v0.4)

> After v0.3.1, two research agents audited the generator for assumptions **overfit to
> HTTP request-serving microservices / the Online Boutique demo** (the first use case).
> The finding reframes #226: v0.3.1 patched *one* off-template case (async workers); the
> real defect is that the **core RED triplet is emitted unconditionally**, i.e. the
> determination model itself assumes every service is a request-server. This pass
> upgrades the spec from "add async_worker" to a general **contract-first determination**
> rule. (The reflective-loop caution: generalize the rule, don't accrete `batch_worker`,
> `cron_worker`, … as siblings.)

**The overfit, in one line:** convention answers *"what does a request-server emit"*; it must **not** be used to answer *"is this a request-server, and if not, what is it"* — yet today's unconditional triplet + `_ensure_red_coverage` synthesis (`artifact_generator_generators.py:795`) does exactly that.

**What the audit found (representative; full catalog in the research report):**

| Decision point | file:line | Overfit class | Breaks for |
|----------------|-----------|---------------|------------|
| `_GENERATORS` triplet emitted unconditionally | `artifact_generator.py:509` | request-serving-only | cron/batch (no availability%/p99), workers |
| `_ensure_red_coverage` **synthesizes** rate/error/availability panels for every service | `artifact_generator_generators.py:795` | request-serving-only (ROOT) | worker/batch/stream/cron get fabricated "Request Rate" panels |
| Duration-histogram gate (`type==histogram and "duration" in name`) is the *only* SLI path | `generators.py:218/934` | request-serving-only | any service whose primary SLI is a counter/gauge/age ⇒ **zero** alerts/SLOs (the pilot's 6-of-7) |
| `_DEFAULT_THRESHOLDS` = availability 99 / latency 500ms / throughput 100rps | `generators.py:40` | request-serving-only | worker/batch/cron (category-error units) |
| `_PROFILES` = only http/grpc/span-metrics | `metric_descriptor.py:127` | request-serving-only | no queue-depth/last-success/lag surface |
| Transport is a **required** field; no-transport services dropped | `artifact_generator_context.py:298` | request-serving-only | workers/cron/batch have no listen transport ⇒ never generated |

**The general principle (now FR-12):** artifacts are derived from a **resolved SLI-kind set** per service — declared (`kind` + `functional[].signal_kind`) with **convention as fallback only within the request-serving family**. Every alert/SLO/panel is a per-SLI-kind template row. The codebase already has this pattern in miniature: `_EXTENDED_PER_SERVICE_GENERATORS` is contract-driven (emitted iff declared, `artifact_generator.py:200/556`). This pass **promotes that pattern to govern the core triplet** and **deletes** the unconditional RED synthesis (FR-13). A plain request-server with no declaration resolves to `{latency, availability, throughput}` ⇒ **byte-identical** to today (FR-0/FR-11 preserved).

**Precedent in-repo:** `stakeholder_panel/facilitation.py:1156` already fixed this exact anti-pattern ("the old fixed Online-Boutique class silently mis-forecast every non-OB project" → now derived from the project's objective). Same inversion, different subsystem.

**Cross-generator scope (honest bound):** the smell is concentrated in `observability/`. The app-skeleton generators (`backend_/frontend_/scaffold_codegen`, `presentation_polish`) are well-hardened (contract-derived, graceful fallbacks). The one sibling instance is **#77** (`view_codegen` `workspace` archetype overfit to the *polymorphic* shape) — same root pattern, tracked separately (its crash is already fixed on main; the non-polymorphic renderer is the open half).

### 0.4 Reconciliation with #234 — compose, don't duplicate (v0.6)

> A concurrent effort, **PR #234 "importance-scaled SLO default thresholds"** (merged 2026-07-22), shipped its *own* "FR-7": a criticality-scaled threshold table (`config/importance_thresholds.yaml`, `obs_config.load_importance_thresholds`, `_select_importance_default`, resolved in `_resolve_threshold`). It reshapes the **same** `_resolve_threshold` table this doc's FR-7 targets. Discovered while implementing Phase 2a.

- **They are complementary axes of one table, not rivals.** #234 owns the **criticality** axis (magnitude of availability/latency per critical/high/medium/low); #226 FR-7 owns the **signal_kind** axis (which SLI *dimensions* exist: adds queue_depth/retry_rate/freshness/…). Composed: a **criticality × signal_kind** table.
- **The compose needs no new resolution code.** `_resolve_threshold` / `_select_importance_default` are **already generic over `field_name`**, so adding signal_kind cells to `importance_thresholds.yaml` + baselines to `_DEFAULT_THRESHOLDS` is sufficient — the manifest→importance→flat tier logic applies unchanged (extend-vs-build-separate; Accidental-Complexity anti-principle). FR-7 rewritten accordingly.
- **Decision:** compose onto #234's table (user, 2026-07-22). Do **not** build a parallel signal_kind threshold mechanism.
- **Byte-parity intact:** availability/latency for existing services keep resolving through #234's path exactly as today (the Phase-0 goldens already lock this — they were verified green against `main + #234`).

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
- **CR-3 — Onboarding metadata carries service kind.** `instrumentation_hints[svc].kind ∈ {http_server, grpc_server, async_worker, batch, cron, stream, ml_inference, unknown}` *(generalized v0.4)*, producer-supplied (inferred where possible: queue/worker-library import ⇒ worker/stream; **no listen port ⇒ worker/cron/batch** — the same detection mechanism that supplies `detected_databases`). The producer SHOULD also relax the transport-required drop so a service that declares a `kind` is not excluded for lacking a listen transport (`artifact_generator_context.py:298`).

## 3. Requirements (SDK — this repo)

### Back-compat gate
- **FR-0 — Golden regression test first.** Before any generator change, add a full-YAML golden/snapshot test under `tests/unit/observability/` for a **fixture matrix** (per CRP R1-S3), not a single service — because a lone fixture that happens to carry a duration histogram + availability masks the parity risks the later phases touch. The matrix MUST include at least: (a) an `http_server` **with `availability` set** (gates FR-13a's gauge carve-out), (b) a **counter-only** http service with no duration histogram (gates FR-12a's AND-composition), (c) a `grpc_server`. Every later FR runs against it. (None exists today.)

### Determination model (the general rule — the core of v0.4)
- **FR-12 — Contract-first, SLI-kind determination.** Each service SHALL resolve to a **set of SLI kinds** it is observed by, via one deterministic resolver `resolve_sli_kinds(kind, functional[], transport)`: the union of declared `functional[].signal_kind` and `kind`-implied defaults, falling back to `{latency, availability, throughput}` **only when nothing is declared AND the transport is request-serving**. Empty-and-non-request ⇒ `∅` + a visible coverage gap (FR-9), **never** a silent HTTP triplet. Every alert/SLO/dashboard-panel is derived **per SLI kind** from a per-kind template row. Convention answers "what does a request-server emit"; it does not answer "is this a request-server."
  - **FR-12a — Composition rule (byte-parity, per CRP R1-F1/S5).** The SLI-kind gate is **ANDed with** the existing per-metric emission gates (`type=="histogram" and "duration" in name`, `artifact_generator_generators.py:218/934`) — it **never replaces** them. A block emits iff *(its SLI kind ∈ resolved set)* **AND** *(its source metric is present)*. This is the exact guard that keeps a plain http service byte-identical: a service resolving to `{latency,…}` but carrying a counter-only surface still emits no latency block, as today.
  - **FR-12b — Hybrid services (per CRP R1-F5/S6).** A service MAY be observed by more than one workload profile (e.g. a Rails app that both serves HTTP and runs Sidekiq). `kind` is therefore modeled as **one-or-more** kinds; `resolve_sli_kinds` **unions** the per-kind default sets. A hybrid emits the http latency SLO **and** the worker queue_depth SLI, and receives **no** `http_server_duration` SLO on its worker series.
  - **FR-12c — Transport-drop is a hard SDK dependency (per CRP R1-F6/S1).** The `∅ ⇒ coverage-gap` path is **unreachable** while `extract_service_hints` hard-drops any hint with no `transport` (`artifact_generator_context.py:298`, `continue`). Relaxing that drop for a hint that declares a `kind` is an **SDK-side requirement of FR-12/FR-9** (see FR-14), not merely the producer *SHOULD* in CR-3.
- **FR-13 — Delete unconditional RED synthesis.** `_ensure_red_coverage` (`artifact_generator_generators.py:795`) SHALL become `_ensure_signal_coverage(panels, sli_kinds, …)` — it backfills only the panels the resolved SLI-kind set implies, and is a **no-op** when the set implies none. The always-on request-rate/availability synthesis is **removed**, not merely skipped for one kind. This is the single load-bearing deletion; it is the root cause of the wrong output for *every* non-request class, not just workers.
  - **FR-13a — Availability (1h) gauge carve-out (per CRP R1-F2/S2).** The **Availability (1h) gauge** (`artifact_generator_generators.py:876–905`) fires on `business.availability` **alone**, independent of the `has_rate and has_error` early-return — it is an **`availability`-kind** artifact, not a RED-completion panel. `_ensure_signal_coverage` SHALL re-emit it iff *(availability ∈ sli_kinds)* AND *(business.availability set)*. A naive "delete synthesis" that only backfills rate/error panels would silently drop this gauge for every http fixture with an availability SLO; the FR-0 golden fixture MUST include an availability-set service to catch it.
  - **FR-13b — Reuse presence detectors verbatim (per CRP R1-F8/S8).** `_ensure_signal_coverage` MUST reuse the exact `has_rate`/`has_error` detectors (`has_rate_panel`/`has_error_panel`, with the inline fuzzy fallback at `generators.py:820`), not re-derive presence — otherwise a fixture that currently trips the heuristic changes output and breaks FR-11 byte-identity.

### Consume + derive
- **FR-4 — Partial-forward, don't re-author.** Consume forwarded FR ids + traceability (CR-2). Only the genuinely-absent `signal_kind`/`target`/`service` are authored/declared; the ids, feature/task mappings, and source references come from `ingestion-traceability.json` unchanged.
- **FR-5 — Signal-kind is the primary derivation axis.** The core triplet's emission is itself `signal_kind`-gated (FR-12), not unconditional. Read `spec.requirements.functional[]`; derive artifacts per `signal_kind`. **Normative `signal_kind` enum (owned here), each with a one-line gloss (metric shape · query template · default unit) to keep members orthogonal (per CRP R1-F3/F4):**
  - `availability` — success ratio over a request counter · `1 - errors/total` · percentunit
  - `latency` — duration histogram · p99 bucket · seconds
  - `throughput` — request/op counter · `rate()` · rps
  - `queue_depth` — backlog gauge · instantaneous depth · items
  - `retry_rate` — **retries/sec** counter (rate-shaped, *distinct from* `run_success`) · `rate(retries_total)` · per-sec
  - `run_success` — **success ratio with an error-budget** over run outcomes (budget-shaped) · `succeeded/total` over N runs · ratio
  - `freshness` — **age since last success** (monotonic between successes) · `time() - last_success_ts` · seconds
  - `lag` — **backlog magnitude / consumer-offset behind head** (unbounded gauge, *distinct from* `freshness`) · offset/items behind · items or seconds-behind
  - `saturation` — resource utilization gauge · `used/capacity` · percentunit
  - `custom` — declared PromQL + target, escape hatch

  At minimum the non-request kinds (`queue_depth`, `retry_rate`, `freshness`, `run_success`, `lag`, `saturation`) gain derivation paths beyond today's availability+latency. Additive by default (OQ-6); a kind MAY suppress a default SLI (workers suppress latency). The `retry_rate`/`run_success` and `lag`/`freshness` distinctions are load-bearing: they select *different* template rows and *different* threshold units (FR-7), so authoring them interchangeably is a category error.
- **FR-6 — Kind→profile table (general, not one row).** Extend `MetricDescriptor._PROFILES` with a **table** of workload profiles — ship `http_server`, `grpc_server`, `async_worker`, **`batch`, `cron`, `stream`** (+ their SLI series/selectors) — plus one `kind→profile` map beside `_TRANSPORT_DEFAULTS`; thread `kind` into `resolve_descriptor` so kind wins over transport. `profile_for_transport`'s HTTP fallback survives **for the request-serving family only**. The requirement is the *table + resolution tier*; each row is ~4 additive lines. No service shall receive an SLI on series it does not emit (e.g. a worker on `http_server_duration`).
- **FR-7 — Per-SLI-kind default thresholds, *composed onto the #234 importance table* (revised — see §0.4).** A `freshness`/`queue_depth`/… FR on *any* service gets a signal-kind-appropriate default, decoupled from the service's kind. **Composition, not a new mechanism:** PR #234 (merged 2026-07-22) shipped `config/importance_thresholds.yaml` + `_select_importance_default` + `load_importance_thresholds`, a `<criticality>.<mode>.<field>` table resolved in `_resolve_threshold` (`artifact_generator_generators.py:129`). That resolver is **already generic over `field_name`**, so FR-7 is delivered by: (i) adding the non-request `signal_kind` cells (`queue_depth`/`retry_rate`/`freshness`/`run_success`/`lag`/`saturation`) into the **same** `importance_thresholds.yaml` under each criticality (→ a **criticality × signal_kind** table), and (ii) seeding a criticality-agnostic baseline for each in the flat `_DEFAULT_THRESHOLDS`. **No new resolution code** — the existing manifest→importance→flat tiers apply unchanged (extend-vs-build-separate; Accidental-Complexity). `business.default_thresholds` override plumbing already exists.
  - **FR-7 grounding gate (OQ-5).** The threshold *values* and the derivation that *reads* them (FR-5/FR-6) are gated on OQ-5 (real worker/batch/stream series + realistic thresholds). Ship the table *shape* now; fill values from a grounded pilot, not by invention.

### Traceability + visibility
- **FR-8 — Stamp originating FR id on outputs.** Each FR-derived SLO/alert records its source FR id via a `DerivationTrace` (or a `source_fr` field on `ArtifactResult`), surfaced in `observability-manifest.yaml`.
- **FR-9 — FR + SLI-kind coverage report.** The generation report SHALL surface coverage, mirroring `_record_unimplemented_artifact_types`, **distinguishing two gap classes (per CRP R1-F9/S7):** (i) **`resolved=∅`** — a service that resolved to no SLI kinds (no `kind`, non-request); and (ii) **`resolved≠∅, produced=0`** — a declared `signal_kind`/FR whose source metric was absent so it yielded nothing (**the pilot's actual "6 of 7 FRs → nothing" symptom** — the *unfulfilled* class, semantically distinct from ∅). Reporting only ∅ would still mask the original symptom. Both surface in the report instead of being hidden by fabricated RED panels.

### Invariants + docs
- **FR-11 — Absent-input parity (constructive).** With no `functional[]` and no `kind`, output is **byte-identical** to pre-#226 for every service (gated by FR-0). New fields are optional; absence degrades to today's convention path.
- **FR-10 — Supersede the design doc.** Update `UNIFIED_OBSERVABILITY_MANIFEST_REQUIREMENTS.md` (or add an ADR) recording that per-FR derivation + the manifest-schema extension are now in-scope, reversing the prior non-goals.
- **FR-14 — `transport` optional; relax the SDK transport-drop (per CRP R1-F6/F7/S1).** `ServiceHints.transport` (`artifact_generator_models.py:36`, today required `str`) becomes **optional**, and `extract_service_hints` (`artifact_generator_context.py:298`) SHALL admit a hint that declares a `kind` even with no transport (instead of `continue`-dropping it). Precedence when both absent: `unknown` kind ⇒ `∅`. Without this, FR-12c's ∅-path and FR-9's unfulfilled/∅ report are dead code SDK-side.

---

## 4. Non-Requirements

- **NR-1 — No target-project code introspection.** Derive from declared FRs + convention metrics only (the prior doc's rejection stands).
- **NR-2 — No new telemetry runtime.** Changes *what artifacts are derived*, not how the target app is instrumented.
- **NR-3 — Ship the general kind→profile table; defer per-kind authoring guidance, not the mechanism.** *(Revised v0.4 — the prior "defer batch/cron/stream" was itself the overfit.)* Ship the `http_server`/`grpc_server`/`async_worker`/`batch`/`cron`/`stream`/`unknown` rows now (each is cheap + additive). What is deferred is polished per-kind *authoring guidance / runbook prose*, not the determination mechanism. Truly exotic archetypes (ml_inference specifics like GPU saturation series) may land as later rows without spec change.
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

*v0.6 — Phase 2a started. FR-14 (relax transport-drop, add ServiceHints.kinds) SHIPPED (PR #238, merged). §0.4 records the reconciliation with concurrent PR #234 (importance-scaled thresholds): FR-7 recomposed to extend #234's criticality table with a signal_kind axis — no new resolution code (the resolver is already field_name-generic). FR-6/FR-5/FR-7 values gated on OQ-5 grounding.*
*v0.5 — Post CRP Round 1 (claude-opus-4-8). All 9 F-suggestions ACCEPTED + applied (dispositions in Appendix A): FR-12a (AND-composition byte-parity rule), FR-12b (hybrid multi-kind union), FR-12c + FR-14 (relax the SDK transport-drop — the ∅-path was dead code), FR-13a (Availability-gauge carve-out), FR-13b (reuse presence detectors verbatim), FR-5 enum glosses (retry_rate vs run_success, lag vs freshness orthogonality), FR-9 two gap classes (∅ vs unfulfilled — the pilot's real symptom), FR-0 fixture matrix. Two load-bearing claims (transport hard-drop, availability-gauge independence) byte-verified against source before applying.*
*v0.4 — Post de-overfit generalization research (§0.3). Reframed from "add async_worker" to a general contract-first SLI-kind determination model: added FR-12 (SLI-kind determination), FR-13 (delete unconditional RED synthesis); generalized FR-5 (signal_kind primary axis), FR-6 (kind→profile table, not one row), FR-7 (per-signal_kind thresholds), FR-9 (∅-service coverage), NR-3 (ship the table), CR-3 (7-kind enum + no-listen-port inference). Sibling instance #77 (view_codegen) noted; smell bound to observability/. Precedent: stakeholder_panel already fixed this inversion. Ready for CRP.*
*v0.3.1 — Post design-principle hardening. 8 planning corrections; 3 FRs reclassified cross-repo (CR-1..3); FR-6/7 collapsed to profile extension; FR-0 (golden gate) and FR-11 (constructive parity) added; 5 OQs resolved. Applied lessons: phantom-requirement-pruning, phantom-reference-audit, extend-vs-build-separate, vocabulary-single-source. Applied principles: Mottainai, Genchi Genbutsu, Accidental-Complexity, Context-Correctness-by-Construction, Hitsuzen.*

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
| R1-F1 | AND-composition rule for the SLI-kind gate | CRP R1 (opus-4-8) | Applied as **FR-12a**. | 2026-07-22 |
| R1-F2 | Availability (1h) gauge carve-out in FR-13 | CRP R1 | Applied as **FR-13a**; byte-verified `generators.py:876` fires on `business.availability` alone. | 2026-07-22 |
| R1-F3 | `retry_rate` vs `run_success` boundary | CRP R1 | Applied as FR-5 enum glosses (rate-shaped vs budget-shaped). | 2026-07-22 |
| R1-F4 | `lag` vs `freshness` discriminator | CRP R1 | Applied as FR-5 enum glosses (magnitude vs age; different units). | 2026-07-22 |
| R1-F5 | Hybrid multi-kind services | CRP R1 | Applied as **FR-12b** (`kind` = one-or-more; resolver unions). | 2026-07-22 |
| R1-F6 | Transport-drop is a hard SDK dependency | CRP R1 | Applied as **FR-12c** + **FR-14**; byte-verified `context.py:298` `continue`. | 2026-07-22 |
| R1-F7 | `transport` becomes optional | CRP R1 | Applied as **FR-14**. | 2026-07-22 |
| R1-F8 | Reuse exact presence detectors | CRP R1 | Applied as **FR-13b**. | 2026-07-22 |
| R1-F9 | FR-9 distinguish ∅ vs unfulfilled | CRP R1 | Applied to **FR-9** (two gap classes; unfulfilled = the pilot symptom). | 2026-07-22 |

*All 9 R1 F-suggestions ACCEPTED — the review was code-grounded and the two high-severity claims byte-verified before applying. No rejections.*

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8 — 2026-07-22

- **Reviewer**: claude-opus-4-8
- **Date**: 2026-07-22 00:00:00 UTC
- **Scope**: v0.4 de-overfit generalization (§0.3, FR-12/13, generalized FR-5/6/7/9, CR-3). Code-grounded against `observability/{artifact_generator,artifact_generator_generators,artifact_generator_context,metric_descriptor}.py` and `validators/observability_artifact_checks.py`.

**Sponsor focus asks (answered first, per focus file "High-value review axes"):**

- **Ask 1 — Does FR-12 provably preserve byte-identical http output?**
  - **Summary answer:** Partial — provable *only if* the spec states the SLI-kind gate is ANDed with (never replaces) the existing metric-presence gates.
  - **Rationale:** For a plain `http_server`, `resolve_sli_kinds` must yield `{latency, availability, throughput}` (FR-12 says so). But the alert/SLO emitters *already* gate internally on `metric.type=="histogram" and "duration" in name and latency_raw` (`artifact_generator_generators.py:218`, `:934`). If FR-12's per-SLI-kind gate is layered *on top* the output is unchanged; if it is described as *the* gate that decides emission, a service that resolves to `{latency,…}` but carries a *counter-only* surface could now emit a latency block it does not emit today. The spec does not state the composition rule.
  - **Assumptions/conditions:** the resolver runs beside the descriptor (`artifact_generator.py:519`) and the triplet loop stays at `:528`; no change to the per-metric loop bodies.
  - **Suggested improvements:** see R1-F1.
- **Ask 2 — Is deleting `_ensure_red_coverage` (FR-13) safe for every http fixture?**
  - **Summary answer:** Not without one carve-out: the **Availability (1h) gauge** (`artifact_generator_generators.py:876–905`) fires on `business.availability` alone, *independent* of `has_rate`/`has_error`, so it is not a "RED-completion" panel — it is an availability-kind panel that today rides inside `_ensure_red_coverage`.
  - **Rationale:** deleting the synthesis and "backfilling only what the resolved set implies" is safe for the Rate/Error panels (guarded by the `has_rate and has_error` early-return at `:824`), but the availability gauge has no such guard. Any existing http fixture with `availability` set and no pre-existing avail panel *loses the gauge* unless `_ensure_signal_coverage` maps the `availability` SLI-kind to it. General good news for FR-13: RED re-synthesis is genuinely centralized — the dashboard validator only *scores* red_coverage (`observability_artifact_checks.py:285`), it does not re-inject panels, so there is no second synthesis path.
  - **Assumptions/conditions:** the FR-0 golden fixture includes a service with `availability` set (else the regression is invisible).
  - **Suggested improvements:** see R1-F2.
- **Ask 3 — Is the `signal_kind` enum complete/orthogonal?**
  - **Summary answer:** Mostly, with two orthogonality concerns: `retry_rate` overlaps `run_success` (both error-budget-shaped), and `lag` vs `freshness` needs a stated discriminator. See R1-F3, R1-F4.
- **Ask 4 — Kind→profile gap for hybrid services?**
  - **Summary answer:** Yes — real gap. `resolve_sli_kinds(kind, …)` and `ServiceHints.kind` model a *single scalar* kind; a service that both serves HTTP and runs a worker needs two profiles' SLI series. See R1-F5.
- **Ask 5 — OQ-5/OQ-7 non-blocking scoping correct?**
  - **Summary answer:** OQ-5 yes; OQ-7 yes for the SDK seam, but the resolver has a hidden hard dependency on relaxing the transport-drop. See R1-F6.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Validation | high | FR-12 must state the **composition rule**: the resolved-SLI-kind gate is **ANDed** with the existing per-metric emission gates (`type=="histogram" and "duration" in name`, `generators.py:218/934`), never a replacement. A block emits iff (SLI-kind ∈ resolved set) AND (its source metric is present). | Without this, a plain http service that resolves to `{latency,availability,throughput}` but lacks a duration histogram could emit a latency block it does not emit today — a silent parity break FR-0 may miss if the golden fixture happens to carry the histogram. | FR-12 (after "per SLI kind from a per-kind template row") | Parity fixture that resolves to the full triplet but carries only a counter; assert byte-identical to today (empty latency block). |
| R1-F2 | Risks | high | FR-13 must explicitly enumerate the **Availability (1h) gauge** (`generators.py:876`) as a distinct `availability`-kind artifact, not a RED-completion panel; state `_ensure_signal_coverage` re-emits it iff `availability ∈ sli_kinds` AND `business.availability` set. | The gauge fires on `business.availability` alone, bypassing the `has_rate and has_error` early-return; "backfill only what the set implies" is ambiguous about it, so a naive deletion drops the gauge for every http fixture with an availability SLO. This is the concrete FR-13 failure mode. | FR-13 (after "no-op when the set implies none") | FR-0 golden fixture MUST set `availability`; assert the gauge survives the FR-13 rewrite byte-for-byte. |
| R1-F3 | Interfaces | medium | Clarify the `retry_rate` vs `run_success` boundary in the FR-5 enum: is `retry_rate` throughput-shaped (retries/sec) or error-budget-shaped (retry ratio)? If the latter, does it collapse into `run_success`? | As written both look like error-budget-on-a-counter; an implementer cannot tell which template row (rate vs ratio-with-budget) it selects, which propagates divergent thresholds into FR-7. | FR-5, normative enum bullet | One-line semantic gloss per enum member (metric shape + query template + default unit); verify no two glosses are identical. |
| R1-F4 | Interfaces | medium | Give `lag` and `freshness` a stated discriminator: `lag` = backlog/consumer-offset *magnitude* (items or seconds behind head, an unbounded gauge); `freshness` = *age since last success* (seconds, monotonic between successes). | Both are "how stale" signals and will be authored interchangeably otherwise, defeating FR-7's per-signal_kind thresholds — a lag threshold in items ≠ a freshness threshold in seconds (the same category error §0.3 catalogs for `_DEFAULT_THRESHOLDS`). | FR-5 enum gloss (with R1-F3) | `lag`/`freshness` map to *different* default-threshold units in FR-7's table; assert the units differ. |
| R1-F5 | Architecture | high | Add a hybrid-service clause to FR-12/FR-6: a single service MAY resolve to the union of *multiple* kind profiles (e.g. `http_server` ∪ `async_worker`). State whether `kind` is scalar or list and whether the resolver unions per-kind default sets. | `transport` and the proposed `kind` are scalars; `resolve_sli_kinds(kind, …)` takes one kind. A Rails+Sidekiq deploy has no home; the kind→profile table has no hybrid row and NR-3 does not mention union. | New FR-12 clause or FR-6 (after "kind wins over transport") | Fixture with `kind` implying http+worker; assert it emits latency (http) AND queue_depth (worker) SLIs and no `http_server_duration` SLO on the worker half. |
| R1-F6 | Risks | medium | Call out that the resolver's `∅ ⇒ coverage gap` path is **unreachable for transport-less services** because `extract_service_hints` hard-drops any hint with no `transport` (`artifact_generator_context.py:298–301`, `continue`). Make "relax the transport-required drop" a hard SDK dependency of FR-9/FR-12, not only a producer *SHOULD* in CR-3. | If the SDK drops workers before the resolver runs, FR-9's "resolved to ∅" report can never fire — the 6-of-7 symptom stays invisible. This is the load-bearing consume-side change the spec under-scopes. | FR-12 (assumptions) + CR-3 + FR-9 | Fixture: hint with `kind=async_worker`, no `transport`; assert it becomes a ServiceHints and appears in the ∅/`fr_coverage` report instead of being silently skipped. |
| R1-F7 | Data | low | State that `ServiceHints.transport` becomes **optional** once `kind` is present, and define precedence when both absent (`unknown` kind ⇒ ∅). | `transport: str` is currently required (`artifact_generator_models.py:36`); FR-12 depends on a transport-less service surviving, but the requirements name `kind` without stating this model change. | FR-6 or a new FR clause | Schema check: `ServiceHints(transport=None, kind="cron")` constructs and resolves to a non-http profile. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F8 | Validation | medium | FR-11 "byte-identical" is under-specified against the `_ensure_red_coverage` **heuristic RED detection** fallback (`generators.py:820–822`: `"rate(" in e and "_count" in e and "status" not in e`). FR-13's `_ensure_signal_coverage` must reuse `has_rate_panel`/`has_error_panel` verbatim, not re-derive presence, or a fixture that currently trips the heuristic changes output. | The detection is fuzzy string matching; a re-derivation could add/drop a panel the old heuristic suppressed. Byte-identity requires reusing the exact detectors. | FR-13 (implementation note) | Golden fixture whose panels already satisfy RED via the heuristic; assert the FR-13 rewrite adds zero panels. |
| R1-F9 | Ops | low | Define FR-9's handling of **resolved-but-unfulfilled** (signal_kind declared, metric absent, produced=0) vs **resolved-to-∅** (no kind). FR-9 currently conflates them. | The pilot's "6 of 7 FRs → nothing" is the *unfulfilled* class, not the ∅ class; if FR-9 only surfaces ∅ it still masks the original symptom. | FR-9 | Report distinguishes `resolved=∅` from `resolved≠∅, produced=0`; fixture for each. |
