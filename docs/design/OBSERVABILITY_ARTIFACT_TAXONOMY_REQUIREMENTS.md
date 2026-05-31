# Observability Artifact Taxonomy — Requirements

**Date:** 2026-05-31
**Status:** Draft v0.4 — post-CRP-review (R1 triaged: 9/9 F-suggestions applied). Requirements only;
no code this pass. Two-axis model: artifact = (category = *what is observed*, orientation = *who
consumes / acts on it*).
**Lineage:** Consolidates and re-frames `OBSERVABILITY_GENERATION_GAP_ANALYSIS.md`,
`OBSERVABILITY_GENERATION_FOLLOWUP_RUN007.md`, `UNIFIED_OBSERVABILITY_MANIFEST_REQUIREMENTS.md`,
and the pipeline-innate concerns in `cap-dev-pipe/design/pipeline-requirements.md` (REQ-CDP-*).
**Owner module (future code):** `src/startd8/observability/artifact_generator.py` +
`src/startd8/validators/observability_artifact_checks.py`

---

## 0. Planning Insights (self-reflective update, v0.2 → v0.3)

> A planning pass read the three target modules (`artifact_generator.py` ~2400 lines,
> `observability_artifact_checks.py` ~1460 lines, the CLI) to map each requirement to code and
> to surface pre-existing accidental complexity. The headline finding: **this taxonomy is a net
> simplification.** Both axes (category, orientation), once carried as first-class fields, *dissolve*
> five separate accidental-complexity smells. The implementation removes more code-paths than it
> adds. Key corrections below; the opportunistic cleanups are catalogued in Appendix D.

| v0.2 assumption | Planning discovery | Impact on requirements |
|-----------------|--------------------|------------------------|
| REQ-OAT-023 (add category+orientation) is a heavy "L" touching ~40 call sites | Nearly all `ArtifactResult`s flow through `_generate_one` + ~5 helpers; with two lookup tables (`_ARTIFACT_TYPE_TO_CATEGORY` already exists; add `…_ORIENTATION`) assignment is centralized, not 40 hand-edits | 023 reframed as the **keystone** (M, not L); it *unblocks* 020/040/042/051/052 and dissolves the role-bucketing + pseudo-service smells |
| REQ-OAT-040 metric routing is a generation concern | As written it forces brittle name-pattern heuristics (`if "startd8_" in name`) — **new** accidental complexity | **NEW REQ-OAT-024 + revised 040: declare, don't guess** — metadata carries each metric's category/orientation; heuristics are fallback only |
| `_is_non_service_entry` (7 heuristics) is just existing cruft | Same "guessing what metadata should declare" anti-pattern as 040 | Folded into REQ-OAT-024 (structural classification in metadata collapses 7 heuristics → 1 check) |
| REQ-OAT-031 (auto-satisfy) is one requirement for this module | The generator's only job is to **emit** `generation_report` + checksums; the **reuse/auto-satisfy** logic lives in plan-ingestion (cap-dev-pipe), out of this module | 031 **split**: producer (emit, in scope) vs consumer (auto-satisfy, cross-referenced, out of scope) |
| REQ-OAT-013 "migrate the Finding-2 conformant output" | The run-007 Finding-2 fix made `capability_index` *masquerade* as the software-feature schema — the **wrong** direction; it must be reverted, not migrated | 013 reframed as **revert-the-masquerade** → inventory schema |
| REQ-OAT-050 (orientation-aware validation) is "L" | The structural validators are ~90% boilerplate and already near-ready (alerts already check service-label/summary); adding an `orientation` param + a bridge-actionability check is small **once** the 3 validators share a check-runner | 050 is **S–M**; gated on an enabling refactor (unify the 3 boilerplate validators) that itself removes complexity |
| Extensibility was implicit | Five parallel dispatch mechanisms + two parallel scoring paths mean "add an artifact type" currently means "add control flow" | **NEW REQ-OAT-070 invariant**: adding a type MUST be declarative table entries (type→category/orientation/generator/validator), never new dispatch/validation branches |

**Resolved questions:**
- **Per-service vs per-project dispatch (was ambiguous).** Category 1 is per-service; categories 2
  & 3 are per-project (single call, may read all services). Categories 4 & 5 reserved. This is
  now stated in REQ-OAT-042.
- **Where does validator work live?** REQ-OAT-050/061/062 are `observability_artifact_checks.py`
  changes; REQ-OAT-023/040/042/051 are `artifact_generator.py`; auto-satisfy consumer is
  plan-ingestion. Scope boundaries are now explicit per requirement.

*The essential complexity is two declarative axes + two lookup tables + one dispatch table + one
validation runner. Everything else is accidental and collapses (Appendix D).*

---

## 0.1 Motivation

ContextCore generation today treats every produced artifact as one **flat list**:
`onboarding-metadata.json.artifact_types` is a flat enumeration, the generator runs all
types in a single loop, quality scoring applies uniform structural validators, and the
generation manifest records artifacts with no category dimension. This flat treatment is
the root of a recurring class of "looks-like-success" failures (run-003 Gaps 1–5, run-007
Findings 1–3): artifacts of fundamentally different *kinds* are produced, scored, and
reported as if they were the same thing.

Conceptually, every artifact is classified on **two independent axes**:
**category** (§1.1 — *what is observed*: service / business / pipeline-innate / project / agent)
and **orientation** (§1.2 — *who consumes & acts on it*: human, e.g. a dashboard; system, e.g.
a metric / SLI / SLO; or bridge, e.g. an alert or notification policy — system-evaluated,
human-actioned). The flat list collapses both axes, which is why artifacts of fundamentally
different kinds get produced, scored, and reported as if the same. This document defines the
two-axis taxonomy, fixes the `capability_index` naming collision, specifies a category-nested
metadata structure, and defines the pipeline-innate artifact-reuse contract that serial /
project-update runs need.

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

### 1.2 Second axis — artifact orientation (consumer)

Category (§1.1) answers *"what is observed."* It does **not** capture *"who consumes the
artifact and who acts on it,"* which is an independent property. A service dashboard and a
service SLO are both category-1, but a human reads the dashboard while a machine evaluates the
SLO — they need different generation inputs, different validation, and different coverage
accounting. **Orientation** is therefore a second, orthogonal axis. Every artifact is
classified on **both** axes: `(category, orientation)`.

| Orientation | Primary consumer | Artifact types | Validated for |
|-------------|------------------|----------------|---------------|
| **Human-oriented** | a **person** reads / interprets it | `dashboard`, `onboarding_portal`, `role_dashboard`, `runbook` | clarity, completeness, layout, audience-fit, navigability |
| **System-oriented** | a **machine** consumes it | `slo_definition` (SLI + SLO), `service_monitor` (metric collection), recording rules, `provenance`, `generation_report`, `observability_inventory` | schema correctness, parseability, threshold / indicator validity |
| **Bridge (both)** | system-**evaluated**, human-**actioned** | `prometheus_rule` / `alert_rule` (alerting), `loki_rule` (alerting), `notification_policy` | **both** sides: rule validity (system) **and** actionability — severity, annotations, runbook/dashboard links, routing target (human) |

**Why orientation is its own axis (granularity & tracking):**

- **Bridge artifacts are where the system→human handoff happens.** An alert that is
  syntactically valid (system ✓) but has no actionable annotation, no runbook/dashboard link,
  or no notification route (human ✗) is *half-broken* in a way neither a pure-system nor a
  pure-human check would catch. Classifying alerts and notification policies as **bridge** lets
  validation assert **both** halves, and lets reporting track the handoff explicitly.
- **It generalizes the run-007 coverage split.** "dashboarded vs alerted" was an early,
  ad-hoc instance of this axis: *dashboarded* = on a **human** surface; *alerted* = on a
  **bridge** surface. Orientation makes this a principled, complete dimension — a metric's
  coverage is tracked across **human / system / bridge** surfaces (REQ-OAT-061), so a metric
  that is visualized but neither defined as an SLI nor alerted is visibly only 1/3 covered.
- **Mixed-orientation files are explicit.** A `prometheus_rule` / `loki_rule` file may contain
  *recording* rules (system) and *alerting* rules (bridge). The artifact's orientation is
  **bridge-primary**; its recording-rule subset is scored on the system dimension
  (REQ-OAT-062). This is recorded, not hand-waved.

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

**REQ-OAT-013 (revert the masquerade).** The run-007 Finding-2 change made the obs generator's
`capability_index` *conform to the software-feature schema* (`manifest_id`/`version`/`capabilities[]`)
— i.e. it made an observability inventory **masquerade** as a capability manifest. Planning
confirmed this was the wrong direction. The code-alignment pass MUST **revert the masquerade**:
reshape the output to a category-3 **inventory** schema (services + per-category artifact
list/counts/paths) and rename to `observability_inventory` (REQ-OAT-012). It is not a migration
of a correct artifact; it is the removal of a wrong one.

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
authoritative. To keep the flatten deterministic (CRP R1-F3): an artifact type belongs to
**exactly one** category — the same type key appearing under two categories is an **error**, not a
merge — and the flat view's iteration order is **category-declaration order** then within-category
order, so readers that iterate see a stable sequence.

**REQ-OAT-023 (keystone).** Every emitted artifact record (`ArtifactResult`, and entries in the
generation manifest / `generation_report`) MUST carry an explicit `category` field (five-category
enum) **and** an `orientation` field (`human` | `system` | `bridge`). The two are independent;
both are required. These fields MUST be assigned from two declarative lookup tables
(`_ARTIFACT_TYPE_TO_CATEGORY` — already exists; `_ARTIFACT_TYPE_TO_ORIENTATION` — new), populated
centrally (in `_generate_one` and the handful of non-`_generate_one` construction sites), **not**
hand-set at each call site. This requirement is the **keystone**: it unblocks REQ-OAT-020, 040,
042, 051, 052, and is the prerequisite that lets the accidental-complexity cleanups in Appendix D
(D-2 pseudo-service, D-4 role-bucketing) collapse declaratively.

**REQ-OAT-024 (declare, don't guess — structural classification in metadata).** The onboarding
metadata MUST carry the structural facts the generator currently reverse-engineers via heuristics,
so the generator reads them instead of guessing:
- **Entry kind.** Each `instrumentation_hints` entry MUST declare whether it is a real service
  (e.g. `kind: service`). This collapses the seven-heuristic `_is_non_service_entry` filter
  (Appendix D-7) into a single check.
- **Metric category & orientation.** Each declared metric (`manifest_declared[]`, and ideally
  `convention_based[]`) MUST carry its `category` (service / project / agent) and MAY carry
  `orientation`, so metric routing (REQ-OAT-040) is a lookup, not a name-pattern heuristic.

Name-pattern heuristics MAY remain only as a **fallback** when the metadata omits the
classification, and when used MUST be recorded in the generation report as an *inferred* (not
declared) classification, so the gap is visible. This requirement exists because planning showed
REQ-OAT-040, implemented naively, would *add* accidental complexity (brittle metric-name lists);
declaring the facts upstream removes it.

**REQ-OAT-025 (upstream producer — cross-referenced, out of scope).** REQ-OAT-024 requires the
generator to *read* declared structural facts, but onboarding metadata is produced **upstream** by
the cap-dev-pipe onboarding exporter. For "declare, don't guess" to have an actual producer (and not
silently degrade to heuristic-only), the onboarding exporter MUST emit `kind` per
`instrumentation_hints` entry and `category` (and optionally `orientation`) per declared metric.
This is specified here as a cross-referenced contract (mirroring the REQ-OAT-031a/031b split); the
exporter change is tracked in cap-dev-pipe, out of this SDK module's scope. Until it lands, the
generator's heuristic fallback (REQ-OAT-024) is the *primary* path and MUST record each
classification as `inferred`, so the dependency gap is visible, not silent. (CRP R1-F7/S4.)

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

The routing key MUST come from the metric's **declared** category (REQ-OAT-024), not a hardcoded
metric-name list; a name-pattern heuristic is a recorded fallback only. Until categories 4 & 5
have generators (reserved), these metrics MAY remain on a clearly-labeled "domain metrics"
surface, but the generation report MUST record that they are category-4/5 signals awaiting a
category-4/5 home (REQ-OAT-041), so the gap is visible rather than silently mixed into service
observability.

**REQ-OAT-041 (reserved categories).** Categories 4 and 5 MUST be defined and namespaced now,
with no generator required. The taxonomy and metadata MUST accept `project_observability` and
`ai_agent_observability` categories so that (a) their already-emitted metrics have a declared
home, and (b) future generators slot in without re-litigating the taxonomy.

**REQ-OAT-042 (orchestration).** The generator orchestrator SHOULD dispatch by category
(service / business / pipeline-innate), not run all types in one undifferentiated loop, so each
category can have its own preconditions, deploy path, and validators.

### 4.2 Category- and orientation-aware quality validation

**REQ-OAT-050.** Quality validation MUST be both **category-aware and orientation-aware**. Every
generated artifact MUST be scored (closing run-007 Finding 1: `artifacts_scored ==
artifacts_generated`). Honest skips (REQ-OAT-052 — declared-but-unproduced types) are **excluded
from the scored denominator**: a skip is neither generated nor scored, so it does not break the
`scored == generated` invariant and is **not** counted as a 0-score artifact (which would distort
coverage) (CRP R1-F8/S6). Scoring uses validators appropriate to the artifact's
`(category, orientation)`:
- **human-oriented** → clarity / completeness / layout / audience-fit (e.g. dashboard has the
  expected panels & navigation; runbook has all required sections);
- **system-oriented** → schema correctness / parseability / definition validity (e.g. SLO has a
  valid SLI + target; service_monitor has selector/endpoints);
- **bridge** → **both** halves: the rule is valid (system) **and** actionable (human) — severity
  set, summary/annotations present, runbook/dashboard links resolvable, a notification route
  exists. A bridge artifact that passes only one half MUST score as partial, not complete.

> **Feasibility (planning insight).** This is **S–M**, not L: the structural validators
> (`validate_dashboard/alerts/slo`) already perform most system checks and some human checks
> (alerts already verify the `service` label and `summary` annotation). The new work is an
> `orientation` parameter + a small bridge **actionability** check (runbook/dashboard link, a
> non-null notification receiver). It SHOULD be preceded by the enabling refactor in Appendix D-9
> (extract a shared check-runner from the three ~90%-boilerplate structural validators), which
> *removes* complexity and makes the orientation branch trivial.

**REQ-OAT-051 (orientation-based metric coverage).** Per-metric coverage MUST be tracked across
the orientation axis, generalizing the run-007 dashboarded/alerted split:
- `metric_coverage_human` — referenced by a live human surface (dashboard panel);
- `metric_coverage_system` — defined as a system artifact (SLI / recording rule);
- `metric_coverage_bridge` — referenced by an active (non-commented) alert / notification path.

`metric_coverage_human` ≡ the prior `metric_coverage_dashboarded`; `metric_coverage_bridge` ≡
the prior `metric_coverage_alerted` (names retained as aliases for continuity). The composite MUST
fold the three with **equal 1/3 weights** unless a weighting is explicitly documented, so the
headline value is defined and stable (CRP R1-F4): a metric covered on exactly one axis (e.g.
visualized but neither SLI'd nor alerted) reads **≈0.33**, not 1.0 and not 0.0. These are
**service / project / agent** observability dimensions and MUST NOT be applied to pipeline-innate
artifacts.

**REQ-OAT-052 (category-aware honest skip).** Coverage reporting MUST be reported per category.
A declared-but-unproduced type MUST be reported as a skip **with its category and owner** (e.g.
`capability_index — owned by onboarding, not produced by observability`), not as a generic
unimplemented type.

### 4.3 Orientation axis

**REQ-OAT-060.** Every artifact type MUST declare an `orientation` (`human` | `system` |
`bridge`) per the §1.2 table. Orientation is independent of category; generation, validation,
and reporting MUST treat the two axes separately.

**REQ-OAT-061.** Bridge artifacts (`prometheus_rule`/`alert_rule` alerting, `loki_rule`
alerting, `notification_policy`) MUST be validated and reported on **both** the system and human
sub-dimensions (REQ-OAT-050), so the system→human handoff (a valid alert that is nonetheless
unactionable, or a route with no target) is independently visible. Resolution of the runbook
boundary (CRP R1-F5): this generator **does** produce per-service `runbook` artifacts
(`service × human`); a bridge artifact whose `runbook_url`/`dashboard` link points at an artifact
that was **not** produced scores the bridge artifact's **human half as partial** (the handoff is
broken), which is distinct from — and does not double-count with — the runbook's own
human-orientation coverage.

**REQ-OAT-062 (mixed-orientation files).** When a single artifact file contains rules of
differing orientation (e.g. a `prometheus_rule` with both recording and alerting rules), the
artifact's declared orientation is its primary one (bridge), and validation MUST additionally
score the off-orientation subset (recording rules on the system dimension). The breakdown MUST
be recorded, not collapsed.

### 4.4 Extensibility invariant (anti-accidental-complexity)

**REQ-OAT-070 (extension by table, not by control flow).** Adding a new artifact type MUST be
expressible as **declarative table entries** — `type → category`, `type → orientation`,
`type → generator`, `type → validator/contract`, `type → output_path` — and MUST NOT require new
branches in the orchestrator's dispatch or the validator's scoring. This invariant is the
permanent guard against the accidental complexity Appendix D removes (five dispatch mechanisms,
two scoring paths): once dispatch and validation are table-driven, the cost of a new type is one
row, and the taxonomy cannot silently re-accrete special-case control flow. Any change that would
add a per-type `if/elif` branch to orchestration or scoring is a violation of this requirement and
MUST instead extend the relevant table. This prohibition explicitly extends to
**`(category, orientation)`-keyed branches**, not just per-`type` branches (CRP R1-F6): the scoring
dispatcher selects validators from a `(category, orientation) → [validators]` table, and the bridge
"both halves" check (REQ-OAT-050/061) MUST be a property of that table's validator-set for the
`bridge` orientation — **not** an `if orientation == "bridge"` branch in the dispatch body, which
would re-accrete the special-case control flow the table is meant to eliminate.

**REQ-OAT-071 (net-removal acceptance criterion).** The code-alignment pass's headline claim is that
the taxonomy *removes* more complexity than it adds (§0). To keep that falsifiable (CRP R1-F1/S1),
the follow-up PR MUST report the net line delta across the three production modules
(`artifact_generator.py`, `observability_artifact_checks.py`, the CLI — **excluding tests/docs**)
and that delta SHOULD be **non-positive**; a positive delta is permitted only with a recorded
rationale in the PR. This is a **reviewed acceptance criterion**, deliberately **not** an automated
hard line-count CI gate — a rigid line-count fail would itself become accidental complexity (gamed
counts, false failures on legitimate additions). The diff-stat is evidence for the reviewer, not a
build blocker.

### 4.5 Pipeline-innate: generation index, reuse, and serial runs

**REQ-OAT-030 (`generation_report`).** The pipeline MUST emit a `generation_report` (category 3)
that indexes *what was generated this run*, grouped by category, with per-artifact
`{type, category, orientation, service, output_path, status, source_checksum, staleness_inputs}`
and links to the run provenance. Every record carries `category` **and** `orientation` (consistent
with the REQ-OAT-023 keystone), and `source_checksum`/`staleness_inputs` are **mandatory** for the
producer (consistent with REQ-OAT-031a — they are not optional) (CRP R1-F9). This is the artifact
the user described as "a capability index that indexes what has been generated."

> **Scope split (planning insight).** REQ-OAT-031 has a **producer** half and a **consumer** half.
> The producer half — emit `generation_report` with per-artifact source checksums — lives in this
> SDK module (`generate_observability_artifacts` + `_write_index`) and is **in scope** for the
> code-alignment pass. The consumer half — the auto-satisfy reuse logic below — lives in
> **plan-ingestion (cap-dev-pipe)** and is **out of scope** for this SDK module; it is specified
> here as a cross-referenced contract the producer must satisfy. The checksums exist solely for
> the consumer; this module has no use for them itself.

**REQ-OAT-031a (producer — in scope).** `generation_report` MUST record, per artifact, the data
that **fully determines** the consumer's freshness test (REQ-OAT-031b) — since the contract is the
only coordination point across the SDK↔plan-ingestion seam, it must be exhaustive (CRP R1-F2/S3):
- `source_checksum` over the **per-artifact input slice** (only the metadata + manifest fields that
  actually determined *this* artifact), **not** a whole-file hash — a whole-file hash over-invalidates
  (every artifact regenerates on any unrelated metadata edit, a Mottainai loss), a too-narrow hash
  misses real changes (stale reuse);
- a `generator_version` / template-hash component, so a generator/template change invalidates even
  when inputs are unchanged;
- a `staleness_inputs: [...]` list naming the fields that fed the checksum, so the consumer's
  freshness predicate is determined by the report alone (the consumer cannot see SDK internals).

**REQ-OAT-031b (consumer — plan-ingestion, cross-referenced).** When a pipeline run targets
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

## Appendix A — current artifact type → (category, orientation) map

| Current type (code) | Category | Orientation | Notes |
|---------------------|----------|-------------|-------|
| `alert_rule` / `prometheus_rule` | 1 service | **bridge** | alerting = bridge; recording-rule subset scored on system (REQ-OAT-062) |
| `dashboard` (Grafana JSON), `dashboard_spec` (YAML intermediate) | 1 service | **human** | spec is an intermediate, not a declared type |
| `slo_definition` | 1 service | **system** | SLI + SLO target = machine-consumed |
| `service_monitor` | 1 service | **system** | metric-collection (scrape) config |
| `loki_rule` | 1 service | **bridge** | alerting = bridge; recording subset = system |
| `notification_policy` | 1 service | **bridge** | system routing → human delivery |
| `runbook` | 1 service (incident response) | **human** | borderline category; stays with service for now |
| `portal` (today) | 2 business | **human** | → split into `onboarding_portal` + `role_dashboard` |
| `capability_index` (today, obs generator) | 3 pipeline-innate | **system** | → **rename** to `observability_inventory` |
| `provenance` (`run-provenance.json`) | 3 pipeline-innate | **system** | |
| (new) `generation_report` | 3 pipeline-innate | **system** | what-was-generated index |
| `capability_index` (onboarding, software features) | n/a observability | — | owned by onboarding/ContextCore; ceded |

## Appendix B — requirement ID index

`REQ-OAT-010..013` naming/disambiguation · `REQ-OAT-020..023` metadata structure (category +
orientation fields) · `REQ-OAT-030..032` pipeline-innate / reuse · `REQ-OAT-040..042`
category-aware generation · `REQ-OAT-050..052` category- & orientation-aware validation ·
`REQ-OAT-060..062` orientation axis.

## Appendix C — the two axes at a glance

```
                      ORIENTATION  (who consumes / acts)
                  human            system           bridge
              ┌───────────────┬───────────────┬───────────────────┐
   1 service  │ dashboard     │ slo, svc_mon  │ alert, notif_policy│
   2 business │ portal, role  │ —             │ —                  │
C  3 pipeline │ —             │ provenance,   │ —                  │
A             │               │ gen_report,   │                   │
T             │               │ obs_inventory │                   │
E  4 project  │ (reserved)    │ (reserved)    │ (reserved)        │
G  5 agent    │ (reserved)    │ (reserved)    │ (reserved)        │
              └───────────────┴───────────────┴───────────────────┘
   (runbook = service × human; recording-rule subset of alert/loki = service × system)
```

## Appendix D — pre-existing accidental complexity to eliminate (opportunistic)

The planning pass catalogued accidental complexity that has accrued across the Gap 1–5 / Closure
3B / run-007 work. The taxonomy code-alignment pass SHOULD remove these opportunistically — most
*collapse for free* once the two axes (REQ-OAT-023) are first-class. "Adds/removes" is relative
to the codebase, not the requirements. Effort S/M/L.

| # | Smell | Location (artifact_generator.py unless noted) | Why accidental | Distillation | Effort |
|---|-------|-----------------------------------------------|----------------|--------------|--------|
| D-1 | **Five parallel dispatch mechanisms** (triplet loop, extended dict loop, dashboard-JSON convert, portal, capability_index) all produce `ArtifactResult` yet each has bespoke control flow | orchestrator `generate_observability_artifacts` | uniform problem, five shapes; adding a type means picking a mechanism | one **category-aware dispatch table** (REQ-OAT-042/070) | M |
| D-2 | **capability_index as project pseudo-service** — emitted with `service_id=project_id`, so the quality report's `services` dict gets a fake "service" with a spurious composite | `generate_capability_index`; `_write_quality_report` | shortcut to reuse the per-service loop; semantic lie | bucket category-3 artifacts in a separate `pipeline`/`project` report section (REQ-OAT-052); collapses once `category` exists | S |
| D-3 | **`dashboard_spec` vestigial intermediate** — the YAML spec is persisted *and scored* as an end artifact though it only feeds the Grafana-JSON conversion | `generate_dashboard_spec`, `_convert_dashboards_to_grafana_json`, `_CAPABILITY_INDEX_EXCLUDE` | the JSON was added later (Gap 4); the spec was never demoted | mark `status="intermediate"` (skip write/scoring) or inline it; declare only `dashboard` (JSON) | M |
| D-4 | **Role-bucketing by artifact-type name** (`if type in ("dashboard_spec","dashboard")` → dashboarded; `=="alert_rule"` → alerted) | `_write_quality_report` | conflates *type* with *orientation*; breaks when types multiply | declarative `group_by(orientation)` once `orientation` exists (REQ-OAT-051) | S |
| D-5 | **Two parallel scoring paths** — `_repair_and_validate` (triplet, rich validators, if/elif) vs `_score_extended_artifacts` (generic substring, separate pass) | both functions | triplet existed first; extended bolted on for run-007 Finding 1 | one `(category,orientation)`-aware scoring dispatcher (REQ-OAT-050) | M |
| D-6 | **Dead/inert code**: `compute_service_composite` exported in `__all__` but never called; `repair_gridpos` call is a no-op since gridPos is stamped at generation; dangling `compute_service_composite` comment | `observability_artifact_checks.py:645,36`; `artifact_generator.py` gridpos path | superseded by later fixes, never removed | delete | S |
| D-7 | **`_is_non_service_entry` seven heuristics** (req-id, run-id, project-name, dir-names, suffixes, multi-word…) | `_is_non_service_entry` | metadata doesn't declare entry kind, so the code guesses | one check on declared `kind` (REQ-OAT-024) | S |
| D-8 | **Duplicated magic weights** `_STRUCTURAL_WEIGHT/_COVERAGE_WEIGHT` in the validator **and** `_COMPOSITE_*_WEIGHT` in the generator; hardcoded default thresholds | `observability_artifact_checks.py:641`, `artifact_generator.py:~149,~2146` | copy-paste; can drift | one shared constants block | S |
| D-9 | **Three structural validators are ~90% boilerplate** (same parse / count / issues / repair pattern) across `validate_dashboard/alerts/slo`; 5 near-identical result dataclasses | `observability_artifact_checks.py` | grew one-at-a-time | extract a shared **check-runner** + base result; *enables* REQ-OAT-050 cheaply | M |
| D-10 | **CLI `--portal-persona=all` special branch** bifurcates the CLI and re-loads metadata (`load_onboarding_metadata`/`extract_service_hints`/`load_business_context` a second time) | `scripts/generate_observability_artifacts.py` | special case leaked into the CLI | move the persona fan-out inside the generator; CLI stays flat | S |
| D-11 | **`TODO-when-absent` domain-alert stub machinery** (`_domain_alert_todo_block`) becomes obsolete once domain metrics route to categories 4/5 (REQ-OAT-040) | `_domain_alert_todo_block`, alert assembly | workaround for "no home for domain metrics" | remove when metric routing lands | M |

**Net:** D-2/D-4/D-7 collapse *for free* with the REQ-OAT-023 keystone + REQ-OAT-024 metadata.
D-6/D-8/D-10 are standalone quick wins (do anytime). D-9 is an enabling refactor that *lowers* the
cost of REQ-OAT-050. D-1/D-5 are the two structural unifications that REQ-OAT-042/050/070 mandate.
The code-alignment pass should net **remove** lines, not add them.

---

*v0.3 — Post-planning self-reflective update. Reframed 1 keystone (023), added 2 requirements
(024 declare-don't-guess, 070 extension-by-table), split 1 (031 → producer/consumer), corrected 2
(013 revert-not-migrate, 050 effort S–M), resolved 2 questions, and catalogued 11 pre-existing
accidental-complexity items (Appendix D) the implementation should remove. Net finding: the
taxonomy is a simplification — implementation removes more complexity than it adds.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-F{n}` for this requirements doc).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-F1 | Measurable net-removal invariant | R1 (opus-4-8) | Applied as **REQ-OAT-071**, but as a *reviewed* acceptance criterion (diff-stat evidence), **not** a hard CI line-count gate — a rigid gate is itself accidental complexity | 2026-05-31 |
| R1-F2 | Checksum granularity + generator_version + staleness_inputs | R1 | Applied to **REQ-OAT-031a** (per-artifact input slice; generator/template hash; `staleness_inputs` list) | 2026-05-31 |
| R1-F3 | Flatten precedence / duplicate-key rule | R1 | Applied to **REQ-OAT-022** (type ∈ exactly one category → dup is error; order = category-declaration order) | 2026-05-31 |
| R1-F4 | Specify 3-way coverage blend weights | R1 | Applied to **REQ-OAT-051** (equal 1/3; single-axis ≈0.33) | 2026-05-31 |
| R1-F5 | Runbook ownership + bridge-link failure mode | R1 | Applied to **REQ-OAT-061** (generator produces runbooks; unresolvable link → bridge human-half partial, no double-count) | 2026-05-31 |
| R1-F6 | Forbid `(category,orientation)` if/elif in dispatcher | R1 | Applied to **REQ-OAT-070** (bridge dual-check is a table validator-set property, not a branch) | 2026-05-31 |
| R1-F7 | Upstream exporter requirement for declare-don't-guess | R1 | Applied as **REQ-OAT-025** (cap-dev-pipe onboarding exporter MUST emit `kind`/metric-`category`; fallback recorded as `inferred`) | 2026-05-31 |
| R1-F8 | Skip vs scored denominator | R1 | Applied to **REQ-OAT-050** (skips excluded from denominator; not 0-score) | 2026-05-31 |
| R1-F9 | generation_report record schema consistency | R1 | Applied to **REQ-OAT-030** (record carries category+orientation; checksum/staleness mandatory for producer) | 2026-05-31 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-05-31

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-05-31 00:00:00 UTC
- **Scope**: Requirements review (F-prefix) for the two-axis observability artifact taxonomy. Sponsor focus asks answered first; then ambiguity / testability / completeness suggestions.

##### Sponsor focus-ask answers (orchestrator triages later; not triage)

**Ask 1 — Accidental complexity: does the design actually remove it?**
- **Summary answer:** Partial — net-removal is plausible for the *current* 3 implemented categories, but the two-axis model introduces three new structures (orientation lookup table, unified dispatch table, 3-way coverage blend) whose own complexity is asserted but never bounded.
- **Rationale:** §0 and Appendix D credibly show D-2/D-4/D-7 collapsing once `category`/`orientation` are first-class (REQ-OAT-023/024). But the §0 closing claim "essential complexity is two declarative axes + two lookup tables + one dispatch table + one validation runner" is a *target*, not a verified invariant — there is no acceptance criterion that the net line delta is negative, and REQ-OAT-070 forbids new branches without stating how the table itself is prevented from growing per-`(category,orientation)` special cases (e.g. the bridge "both halves" path in REQ-OAT-050 is itself a conditional). The 5-category enum where only 3 are implemented (§1) is justified by REQ-OAT-041 (declared home for already-emitted metrics) — that is genuine, not speculative, so it is *not* over-abstraction.
- **Assumptions / conditions:** Net-removal holds only if Phases 0–2 land before features (plan's distillation-first ordering) *and* a measured line-delta gate exists; otherwise the claim is unfalsifiable.
- **Suggested improvements:** Add REQ-OAT-071 (measurable invariant: code-alignment pass MUST net-remove lines, asserted by a diff-stat check in the follow-up PR) and tighten REQ-OAT-070 to forbid `(category, orientation)`-keyed `if/elif` in the scoring dispatcher, not just per-`type` branches (see R1-F1, R1-F6).

**Ask 2 — Producer/consumer scope boundary (REQ-OAT-031 split).**
- **Summary answer:** Mostly clean, but the boundary is *under-specified on the producer side* — the producer is told to emit `source_checksum` but never told what determines staleness, so the consumer's freshness test is unspecified across the seam.
- **Rationale:** REQ-OAT-031a says the checksum is "derived from the inputs that determined it (onboarding metadata + manifest)" but does not pin (a) checksum *granularity* — whole-metadata-file vs the per-artifact slice of metadata that actually fed this artifact — or (b) whether template/generator-version is part of the staleness key. REQ-OAT-031b step 2 ("fresh = source-checksum unchanged") then silently inherits that ambiguity: a coarse whole-file checksum invalidates every artifact on any metadata edit (Mottainai violation), while a too-narrow one misses template changes (stale reuse). The producer "has no use for [checksums] itself" (§4.5 note) — correct — but that makes the contract the *only* coordination point, so it must be exhaustive.
- **Assumptions / conditions:** The consumer (cap-dev-pipe) cannot see SDK generator internals, so everything it needs must be in `generation_report`.
- **Suggested improvements:** REQ-OAT-031a MUST specify checksum granularity (per-artifact input-slice) and MUST include a `generator_version` / template-hash component; add a `staleness_inputs: [...]` field per artifact record so the consumer's freshness predicate is fully determined by the report (see R1-F2).

**Ask 3 — Nested `artifact_categories` backward-compat (REQ-OAT-020/022/024).**
- **Summary answer:** Migration is safe for *flat-only* readers but REQ-OAT-022 omits flatten precedence rules, and "declare, don't guess" (REQ-OAT-024) is not realistic without a stated upstream (cap-dev-pipe onboarding-export) change.
- **Rationale:** REQ-OAT-022 says the flat view is the "union of all categories' types" but does not say what happens on a *duplicate type key* across categories (can't occur today, but the spec permits cat-4/5 to reserve overlapping names) or how ordering is preserved for readers that iterate. More critically, REQ-OAT-024 requires onboarding metadata to *declare* `kind:` and per-metric `category`/`orientation` — but §0 itself notes onboarding metadata is produced upstream; nothing in this doc requires the cap-dev-pipe onboarding exporter to emit those fields, so the generator's "read, don't guess" path has no producer until that cross-repo change exists. Without it, REQ-OAT-024's heuristic "fallback" silently becomes the *primary* path.
- **Assumptions / conditions:** Existing readers (onboarding export, plan-ingestion) currently consume flat `artifact_types`.
- **Suggested improvements:** Add flatten precedence + duplicate-key rule to REQ-OAT-022; add an explicit cross-referenced upstream requirement (REQ-OAT-025, mirroring the 031b pattern) obligating the cap-dev-pipe onboarding exporter to emit `kind`/metric-`category` so REQ-OAT-024 is satisfiable (see R1-F3, R1-F7).

**Ask 4 — Orientation-aware validation & coverage (REQ-OAT-050/051/060/061/062).**
- **Summary answer:** The taxonomy is crisp for clear cases but has at least two genuinely ambiguous boundaries (runbook; recording-rule subset of a bridge file), and the 3-way composite blend can distort the headline score unless weighting is specified.
- **Rationale:** Appendix A flags `runbook` as "borderline category … stays with service for now" and §1.2 lists it human-oriented — fine — but REQ-OAT-061's bridge actionability check requires "runbook/dashboard links resolvable," which presumes runbooks *exist as scored artifacts*; nothing says whether a missing-but-linked runbook fails the alert (bridge) or is a separate human-artifact gap. For coverage, REQ-OAT-051 folds human/system/bridge "into the composite" but never gives the blend weights, so a metric visualized (human ✓) but un-SLI'd and un-alerted could read 0.33 or some weighted value — the headline is undefined and could mislead (Ask 4's distortion concern). REQ-OAT-062's "score the off-orientation subset" is crisp.
- **Assumptions / conditions:** Bridge artifacts can reference artifacts (runbooks) that this generator may not itself produce.
- **Suggested improvements:** Specify the 3-way blend (equal-weight 1/3 each, or document the chosen weights) and state whether an unresolvable runbook link is a bridge-partial vs a separate coverage gap; clarify runbook scoring ownership (see R1-F4, R1-F5).

##### Numbered suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Architecture | high | Add a measurable net-removal invariant (REQ-OAT-071): the code-alignment pass MUST produce a non-positive net line delta across the three modules, asserted by a diff-stat check in the follow-up PR | §0 asserts "the taxonomy is a net simplification" and the closing line claims "implementation removes more complexity than it adds," but no requirement makes this falsifiable; an unmeasured simplification claim can silently regress into addition | New REQ-OAT-071 under §4.4 (extensibility invariant), or §5 migration | CI/diff-stat: `git diff --stat` on the follow-up PR shows net deletions in `artifact_generator.py` + `observability_artifact_checks.py` + CLI |
| R1-F2 | Interfaces | high | REQ-OAT-031a MUST specify (a) checksum *granularity* = the per-artifact slice of onboarding metadata + manifest that determined that artifact (not whole-file), and (b) inclusion of a `generator_version`/template-hash component; add a per-record `staleness_inputs` listing | As written ("derived from the inputs that determined it") the checksum scope is ambiguous; whole-file → over-invalidation (Mottainai loss), too-narrow → stale reuse; the consumer (031b) can only be correct if the report fully determines freshness | REQ-OAT-031a body | Unit test: editing an unrelated service's metadata does NOT change artifact X's `source_checksum`; bumping `generator_version` DOES |
| R1-F3 | Data | high | Add flatten precedence + duplicate-key resolution to REQ-OAT-022: define behavior when the same artifact-type key appears under two categories, and state that flat-view iteration order is category-declaration order | "union of all categories' types" is underspecified for collisions and ordering; readers that iterate `artifact_types` (onboarding export, plan-ingestion) could see nondeterministic order or silent overwrite | REQ-OAT-022 | Test: a metadata fixture with a duplicate type key produces a deterministic, documented flat view (error or first-wins, as decided) |
| R1-F4 | Validation | medium | Specify the 3-way coverage composite blend in REQ-OAT-051 (e.g. equal 1/3 weights for human/system/bridge, or document chosen weights) and define the value for a metric covered on only one axis | REQ-OAT-051 says all three "fold into the composite" so a partially-covered metric "reads as partially covered, not 1.0," but never gives weights; the headline coverage number is currently undefined and Ask 4 flags possible distortion | REQ-OAT-051 | Test: a metric on a dashboard only (human ✓, system ✗, bridge ✗) yields the documented composite (e.g. 0.33), not 1.0 and not 0.0 |
| R1-F5 | Validation | medium | Clarify runbook scoring ownership and the bridge-link failure mode: state whether an unresolvable `runbook`/`dashboard` link in a bridge artifact (REQ-OAT-061) scores the *alert* as partial, or is reported as a separate human-artifact coverage gap, and whether this generator produces `runbook` artifacts at all | Appendix A marks runbook "borderline … stays with service for now" and REQ-OAT-061 requires "runbook/dashboard links resolvable," but ownership/production of runbooks is unstated, creating an ambiguous validation case (Ask 4) | §1.2 + REQ-OAT-061 | Test: a bridge alert linking a nonexistent runbook scores per the documented rule (bridge-partial vs separate gap) |
| R1-F6 | Architecture | medium | Strengthen REQ-OAT-070 to forbid `(category, orientation)`-keyed `if/elif` in the scoring dispatcher, not only per-`type` branches; the bridge "both halves" path (REQ-OAT-050) is itself a conditional that could re-accrete special-case control flow | REQ-OAT-070 guards against per-type branches but the unified scoring dispatcher (Phase 2 / REQ-OAT-050) must branch on orientation to run the bridge dual-check; without an explicit table-driven mandate, orientation handling becomes the next accidental-complexity vector | REQ-OAT-070 | Code review: scoring dispatcher selects validators via a `(category,orientation)→validators` table; no orientation `if/elif` in the dispatch body |
| R1-F7 | Interfaces | high | Add a cross-referenced upstream requirement (REQ-OAT-025, mirroring 031b) obligating the cap-dev-pipe onboarding exporter to emit `kind` per instrumentation-hints entry and `category`/`orientation` per declared metric, so REQ-OAT-024 "declare, don't guess" has an actual producer | REQ-OAT-024 requires the generator to *read* declared structural facts, but §0 notes onboarding metadata is produced upstream and no requirement makes the exporter emit them; without it the heuristic "fallback" silently becomes the primary path, defeating the requirement | New REQ-OAT-025 under §3 (or §4.5 cross-reference style) | Integration: an onboarding-metadata fixture from the updated exporter carries `kind`/metric-`category`; generator path takes the declared branch, not the inferred fallback |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F8 | Risks | medium | Resolve the REQ-OAT-050 vs REQ-OAT-052 interaction: a declared-but-unproduced type is an "honest skip" (052), but REQ-OAT-050 requires "artifacts_scored == artifacts_generated" — state explicitly that skips are excluded from the scored denominator, not counted as 0-score artifacts | The Finding-1 invariant (scored == generated) and the honest-skip mechanism can conflict: if a skip is counted as a generated-but-unscored artifact the invariant breaks; if counted as score 0 it distorts coverage. The boundary is currently implicit | REQ-OAT-050 / REQ-OAT-052 | Test: a project declaring `capability_index` (owned by onboarding) shows an honest skip AND `artifacts_scored == artifacts_generated` still holds (skip not in denominator) |
| R1-F9 | Data | low | REQ-OAT-030's per-artifact record `{type, category, service, output_path, status, checksum?}` makes `orientation` optional/absent, but REQ-OAT-023 (keystone) requires every record carry `orientation`; align the two field lists | REQ-OAT-023 mandates `orientation` on "entries in the generation manifest / generation_report," yet the REQ-OAT-030 record schema omits it (and marks checksum optional though 031a makes it mandatory for the producer) — an internal inconsistency an implementer would have to guess through | REQ-OAT-030 record schema | Schema test: every `generation_report` artifact entry has non-null `category` AND `orientation`; producer entries have non-null `source_checksum` |

**Endorsements** (prior untriaged suggestions this reviewer agrees with): none — R1 is the first round; no prior untriaged suggestions exist.

**Disagreements** (prior untriaged items this reviewer would reject): none — first round.
