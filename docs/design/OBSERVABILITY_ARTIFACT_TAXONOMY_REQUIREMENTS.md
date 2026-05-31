# Observability Artifact Taxonomy — Requirements

**Date:** 2026-05-31
**Status:** Draft v0.1 — requirements only (no code changes in this pass)
**Lineage:** Consolidates and re-frames `OBSERVABILITY_GENERATION_GAP_ANALYSIS.md`,
`OBSERVABILITY_GENERATION_FOLLOWUP_RUN007.md`, `UNIFIED_OBSERVABILITY_MANIFEST_REQUIREMENTS.md`,
and the pipeline-innate concerns in `cap-dev-pipe/design/pipeline-requirements.md` (REQ-CDP-*).
**Owner module (future code):** `src/startd8/observability/artifact_generator.py` +
`src/startd8/validators/observability_artifact_checks.py`

---

## 0. Motivation

ContextCore generation today treats every produced artifact as one **flat list**:
`onboarding-metadata.json.artifact_types` is a flat enumeration, the generator runs all
types in a single loop, quality scoring applies uniform structural validators, and the
generation manifest records artifacts with no category dimension. This flat treatment is
the root of a recurring class of "looks-like-success" failures (run-003 Gaps 1–5, run-007
Findings 1–3): artifacts of fundamentally different *kinds* are produced, scored, and
reported as if they were the same thing.

Conceptually, generation produces **five categories** of artifact, distinguished by **what
is being observed** (or, for the pipeline category, what is being *recorded*). Two are
implemented today, one is implemented-but-mislabeled, and two are emergent (their signals
are already emitted but have no home). This document defines the taxonomy, fixes the
`capability_index` naming collision, specifies a category-nested metadata structure, and
defines the pipeline-innate artifact-reuse contract that serial / project-update runs need.

This is a **requirements** document. Code alignment is a separate, follow-up pass.

---

## 1. The five-category taxonomy

| # | Category | Observes / records | Example artifact types | Deploy target | Status |
|---|----------|--------------------|------------------------|---------------|--------|
| 1 | **Service Observability** | a running **service's** health (RED, infra) | `prometheus_rule`, `dashboard`, `slo_definition`, `loki_rule`, `notification_policy`, `service_monitor` | Prometheus / Grafana / Loki / Alertmanager / k8s | Implemented |
| 2 | **Business Observability** | **business outcomes & role views** | `onboarding_portal`, `role_dashboard` | Grafana (audience-scoped) | Partial (portal conflates the two) |
| 3 | **Pipeline / Innate** | the **generation run itself** | `provenance`, `generation_report` (run/generation index), `observability_inventory` | internal (pipeline state) | Implicit / undocumented |
| 4 | **Project Observability** | the **project's development lifecycle** | (reserved) task-progress, burndown, delivery, code-quality | Grafana (project tracking) | Reserved — signals emitted, no generator |
| 5 | **AI Agent Observability** | the **AI agents / LLM workflows** | (reserved) cost, tokens, sessions, agent-trace, eval/quality | Grafana / Tempo (agent telemetry) | Reserved — signals emitted, no generator |

The discriminator is **"whose telemetry / what subject is this?"**:

- (1) Service = the *deployed application at runtime*.
- (4) Project = *building & maintaining* that application.
- (5) AI Agent = the *agents that build it*.
- (2) Business = *outcomes and audiences*.
- (3) Pipeline/Innate = *bookkeeping about the generation process* — it is not "observability
  of" a subject; it records **what was generated** so later stages/runs can reason about it.

### 1.1 Category definitions

**1 — Service Observability.** Per-service technical monitoring derived from OTel convention
metrics × business SLO thresholds. This is the existing triplet (`alert_rule`/`prometheus_rule`,
`dashboard`(+spec), `slo_definition`) plus the extended technical types (`service_monitor`,
`loki_rule`, `notification_policy`). Subject: a deployed service. **Must contain only
service-health signals** — see REQ-OAT-040 on metric routing.

**2 — Business Observability.** Audience- and outcome-oriented views. Split into two distinct
artifact types (REQ-OAT-021): `onboarding_portal` ("what *is* this project / what services
exist") and `role_dashboard` ("what does my role — operator / engineer / manager — need to do
now"). A meta-layer over category 1, not a replacement for it.

**3 — Pipeline / Innate.** Records the generation run. Comprises: `provenance`
(`run-provenance.json`, input→output checksum linkage, REQ-CDP-INT-001); `generation_report`
(a run/generation index of *what was produced* across all categories, enabling project-update
and serial-run coordination — REQ-OAT-030/031); and `observability_inventory` (operator-facing
index of the observability artifacts specifically — the artifact currently mislabeled
`capability_index`, REQ-OAT-012). These are **not** "observability of" a subject; they are
generation metadata.

**4 — Project Observability (reserved).** Observes the *development lifecycle* of the project
being built: task progress, burndown/velocity, delivery and code-quality. Aligns with the
ContextCore "Project O11y / tasks-as-spans" paradigm. **Reserved**: no generator yet, but the
signals already exist (REQ-OAT-041).

**5 — AI Agent Observability (reserved).** Observes the *AI agents and LLM workflows* doing
the work: cost, token burn, active sessions, context-usage, truncations, agent traces, tool
use, eval/quality. **Reserved**: no generator yet; the SDK already emits these metrics
(`costs/`, session tracking) (REQ-OAT-041).

---

## 2. The `capability_index` disambiguation

`capability_index` (and `.agent.yaml`, "capability index") currently names **four distinct
concepts**. This collision is the single largest source of accidental complexity in the
generation layer. The decisions below (adopted) disentangle them.

| # | Concept | Schema / shape | Owner | Decision |
|---|---------|----------------|-------|----------|
| (a) | `/capability-index` skill + `docs/capability-index/startd8.sdk.capabilities.yaml` — manifest of the **software's features** | `manifest_id`/`version`/`capabilities[]` (capability_id, category, maturity, summary, evidence) | startd8-sdk | **Keep** the name `capability_index` |
| (b) | Onboarding contract `artifact_types.capability_index` → `docs/capability-index/contextcore.agent.yaml` — **software features** (same concept as (a)) | same as (a); `schema_url: contextcore.io/schemas/capability-index/v1` | ContextCore export / onboarding | **Cede**: this is the canonical `capability_index`; the observability generator does **not** produce it |
| (c) | Observability generator's `generate_capability_index` output — actually an **observability inventory** | currently ad-hoc `{observability_capabilities, …}` (or, post run-007 Finding 2, a *masquerade* of (a)) | startd8-sdk observability | **Rename → `observability_inventory`** (category 3); stop calling it `capability_index` |
| (d) | The **generation index** intent: index of *what was generated*, for project-update / serial-run reuse | new — `{run_id, generated_at, categories: {…}, artifacts: […], provenance_links}` | none yet | **Formalize → `generation_report`** (category 3) |

**REQ-OAT-010.** The observability generator MUST NOT produce an artifact named
`capability_index`. The `capability_index` concept (a/b) is owned by the onboarding /
ContextCore export path (REQ-CDP-ONB-001) and describes software features, not observability.

**REQ-OAT-011.** When `capability_index` appears in a project's declared artifact requirements
but is owned by onboarding, the observability generator MUST report it via the honest-skip
mechanism (category-aware, REQ-OAT-052) — i.e. *not produced here, owned by onboarding* —
rather than emitting a wrongly-schemaed file.

**REQ-OAT-012.** The observability generator's inventory of the observability artifacts it
produced MUST be named `observability_inventory` and emitted to
`observability-inventory.yaml`. It belongs to category 3 (pipeline/innate). Its schema is an
inventory (services, artifact counts/paths by category), explicitly **not** the
`capability_index` schema. (This reverses run-007 Finding 2 Option A.)

**REQ-OAT-013.** The Finding-2 conformant-`capability_index` output added on
`feat/observability-followup-run007` MUST be migrated to `observability_inventory` per
REQ-OAT-012 in the code-alignment pass.

---

## 3. Category-nested metadata structure

**REQ-OAT-020.** `onboarding-metadata.json` MUST group artifact declarations by category under
an `artifact_categories` key, replacing the flat `artifact_types` enumeration as the
authoritative form:

```yaml
artifact_categories:
  service_observability:
    artifact_types: { prometheus_rule: {...}, dashboard: {...}, slo_definition: {...},
                      service_monitor: {...}, loki_rule: {...}, notification_policy: {...} }
  business_observability:
    artifact_types: { onboarding_portal: {...}, role_dashboard: {...} }
  pipeline_innate:
    artifact_types: { provenance: {...}, generation_report: {...}, observability_inventory: {...} }
  # project_observability:  (reserved)
  # ai_agent_observability: (reserved)
```

Each `artifact_types.<type>` entry keeps its existing fields (`output_path`, `output_ext`,
`schema_url`, `expected_output_contracts`, `parameter_keys`, …).

**REQ-OAT-021.** Business observability MUST be represented as two distinct types —
`onboarding_portal` and `role_dashboard` — not a single `portal` type.

**REQ-OAT-022 (backward compatibility).** A flat `artifact_types` view MUST remain derivable
from `artifact_categories` (union of all categories' types) so existing readers do not break
during migration. Producers SHOULD emit both during the transition; the nested form is
authoritative.

**REQ-OAT-023.** Every emitted artifact record (`ArtifactResult`, and entries in the
generation manifest / `generation_report`) MUST carry an explicit `category` field drawn from
the five-category enum.

---

## 4. Functional requirements

### 4.1 Category-aware generation

**REQ-OAT-040 (metric routing).** Generation MUST route metrics to the category that owns them,
not dump all metrics onto category-1 service dashboards. Specifically the `manifest_declared`
domain metrics MUST route as:

| Metric | Category |
|--------|----------|
| `startd8_cost_total`, `startd8_tokens_total`, `startd8_active_sessions`, `startd8_context_usage_ratio`, `startd8_truncations_total`, `startd8_requests_total`, `startd8_response_time_ms` | 5 — AI Agent Observability |
| `contextcore_task_progress`, `contextcore_task_status`, `contextcore_install_completeness_percent` | 4 — Project Observability |
| `http.server.*` / convention RED metrics | 1 — Service Observability |

Until categories 4 & 5 have generators (reserved), these metrics MAY remain on a clearly-labeled
"domain metrics" surface, but the generation report MUST record that they are category-4/5
signals awaiting a category-4/5 home (REQ-OAT-041), so the gap is visible rather than silently
mixed into service observability.

**REQ-OAT-041 (reserved categories).** Categories 4 and 5 MUST be defined and namespaced now,
with no generator required. The taxonomy and metadata MUST accept `project_observability` and
`ai_agent_observability` categories so that (a) their already-emitted metrics have a declared
home, and (b) future generators slot in without re-litigating the taxonomy.

**REQ-OAT-042 (orchestration).** The generator orchestrator SHOULD dispatch by category
(service / business / pipeline-innate), not run all types in one undifferentiated loop, so each
category can have its own preconditions, deploy path, and validators.

### 4.2 Category-aware quality validation

**REQ-OAT-050.** Quality validation MUST be category-aware. Every generated artifact MUST be
scored (closing run-007 Finding 1: `artifacts_scored == artifacts_generated`), using validators
appropriate to its category — service-observability validators check live alerting / RED
coverage; pipeline-innate validators check inventory/report completeness; etc.

**REQ-OAT-051.** Metric coverage MUST distinguish *dashboarded* from *alerted* per run-007
Finding 3 (`metric_coverage_dashboarded`, `metric_coverage_alerted`), and these are
**service-observability** dimensions — they MUST NOT be applied to pipeline-innate artifacts.

**REQ-OAT-052 (category-aware honest skip).** Coverage reporting MUST be reported per category.
A declared-but-unproduced type MUST be reported as a skip **with its category and owner** (e.g.
`capability_index — owned by onboarding, not produced by observability`), not as a generic
unimplemented type.

### 4.3 Pipeline-innate: generation index, reuse, and serial runs

**REQ-OAT-030 (`generation_report`).** The pipeline MUST emit a `generation_report` (category 3)
that indexes *what was generated this run*, grouped by category, with per-artifact
`{type, category, service, output_path, status, checksum?}` and links to the run provenance.
This is the artifact the user described as "a capability index that indexes what has been
generated."

**REQ-OAT-031 (project-update / serial-run reuse — auto-satisfy).** When a pipeline run targets
a project that was previously generated, plan-ingestion MUST load the prior
`generation_report` / `run-provenance.json` artifact inventory and, before requesting
generation:
1. match required artifacts (from the requirement/coverage contract) against the prior inventory;
2. mark already-present artifacts `auto-satisfy: true` (skip regeneration) when fresh
   (source-checksum unchanged);
3. mark changed/missing artifacts for (re)generation;
4. emit a **delta report** (new / updated / preserved) so serial runs are auditable.

This realizes the Mottainai principle (no needless regeneration) and is the contract that the
"more than one PrimeContractor run in series" and "update an existing project" use cases depend
on. (Folds the workflow review's proposed REQ-CDP-INT-008/009 into this taxonomy.)

**REQ-OAT-032 (intent direction).** Requirements MUST state which artifact is authoritative for
each direction of intent: the requirement/coverage contract (CRD-style) declares **what is
needed** (prospective); `generation_report` / `observability_inventory` record **what was
produced** (retrospective). Coverage = needed vs produced. These MUST NOT be conflated.

---

## 5. Migration & backward compatibility

- **M1.** Introduce `artifact_categories` (REQ-OAT-020) alongside a derived flat `artifact_types`
  view (REQ-OAT-022). No hard break for existing readers.
- **M2.** Rename observability `capability_index` → `observability_inventory` (REQ-OAT-012/013).
  The obsolete `capability_index` output is removed from the observability generator's declared
  types.
- **M3.** Split `portal` → `onboarding_portal` + `role_dashboard` (REQ-OAT-021).
- **M4.** Add `category` to `ArtifactResult` / generation manifest (REQ-OAT-023).
- All migrations are code-alignment work for the **follow-up pass**; this document defines the
  target behavior only.

---

## 6. Out of scope (this pass)

- Implementing category-4 (project observability) and category-5 (AI agent observability)
  generators. They are **reserved/defined** here; implementation is future work.
- The content hardening of category-1 extended scaffolds (notification webhook, loki rate
  gating, runbook sections) — tracked in the run-007 appendix; surfaced by REQ-OAT-050 scoring.
- Any code changes. This is requirements-only.

---

## Appendix A — current artifact type → category map

| Current type (code) | Category | Notes |
|---------------------|----------|-------|
| `alert_rule` / `prometheus_rule` | 1 service | |
| `dashboard` (Grafana JSON), `dashboard_spec` (YAML intermediate) | 1 service | spec is an intermediate, not a declared type |
| `slo_definition` | 1 service | |
| `service_monitor`, `loki_rule`, `notification_policy` | 1 service | technical infra |
| `runbook` | 1 service (incident response) | borderline; stays with service for now |
| `portal` (today) | 2 business | → split into `onboarding_portal` + `role_dashboard` |
| `capability_index` (today, obs generator) | 3 pipeline-innate | → **rename** to `observability_inventory` |
| `provenance` (`run-provenance.json`) | 3 pipeline-innate | |
| (new) `generation_report` | 3 pipeline-innate | what-was-generated index |
| `capability_index` (onboarding, software features) | n/a observability | owned by onboarding/ContextCore; ceded |

## Appendix B — requirement ID index

`REQ-OAT-010..013` naming/disambiguation · `REQ-OAT-020..023` metadata structure ·
`REQ-OAT-030..032` pipeline-innate / reuse · `REQ-OAT-040..042` category-aware generation ·
`REQ-OAT-050..052` category-aware validation.
