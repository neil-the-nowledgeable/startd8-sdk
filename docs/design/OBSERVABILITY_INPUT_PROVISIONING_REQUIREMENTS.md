# Observability & Onboarding Artifact Input Provisioning — Requirements

**Date:** 2026-05-31
**Lineage:** Follows `OBSERVABILITY_GENERATION_GAP_ANALYSIS.md` (run-003) and
`OBSERVABILITY_GENERATION_FOLLOWUP_RUN007.md` (run-007 audit). Validated against run-008,
where scoring findings 1–3 were closed but residual **content** defects remain because the
required content cannot be derived.
**Scope:** The cap-dev-pipe observability artifact generator, the onboarding-metadata export,
and the business-observability surface — specifically the **human- and document-provided inputs**
that raise output quality.
**Status:** Draft requirements for review.
**Canonical doc — consolidates:**
- `contextcore-demo-retail/personas/ONBOARDING_SLO_INPUT_CATALOG.md` — the business-KPI /
  role-target catalog + the POLISH→RESOLVE collection mechanism (merged into §5 Group E, §6b, §9).
- `docs/design/OBSERVABILITY_GENERATOR_INPUTS_UPSTREAM.md` — the operational-placeholder inventory
  (runbook_url / webhook receiver / `dashboard_url`) and the REQ-OAT-061 consumer-side connection
  (merged into FR-A2 / FR-B6). That note is now **superseded by this doc** for the producer side.

---

## 1. Overview & Problem

Run-008 proved the generator and scorer are now honest: all 9 artifacts are scored, the
composite reflects real quality (0.7454), and the metric-coverage split exposes that domain
metrics are *dashboarded* (1.0) but not *alerted* (0.077). The remaining low scores and residual
defects are **not generator bugs** — they are **missing inputs**. Some artifact content is
inherently un-derivable from code + conventions and must be supplied by people or source
documents:

- A **runbook's** incident procedures, risks, and escalation path.
- A **notification policy's** real receiver target (webhook/PagerDuty/Slack), not `REPLACE_WITH_WEBHOOK_URL`.
- **Alert thresholds** for domain metrics (cost, tokens, truncations, context-usage) — there is
  no defensible default for "cost too high."
- **Owners / on-call contacts** — currently the placeholder string `contact` and `team@example.com`.

This document catalogs **every input surface the pipeline already exposes**, identifies the
**content gaps** that need provisioning, and specifies requirements for supplying that content
two ways: as **setup/config** (the manifest, stable per project) and as a **polish-stage
supplemental input** (per-run human/document content merged before EXPORT).

---

## 2. Pipeline Stages & Where Inputs Enter

```
Stage 0 CREATE → Stage 1 POLISH → Stage 1.5 ANALYZE → Stage 2 INIT → Stage 2.5 RESOLVE
   → Stage 3 VALIDATE → Stage 4 EXPORT → (onboarding-metadata.json) → INGESTION → generation
```

- **Stage 1 POLISH** today is a *plan quality gate* (checks the plan doc has overview /
  objectives / risks / requirements sections — see `polish-report.json`). It validates the
  **input plan**, it does not yet enrich artifact content. **The flag point** — where a missing
  catalogued input becomes a visible clarity gap (see FR-C2 / FR-E1).
- **Stage 2 INIT** bootstraps the manifest (`.contextcore.yaml`) from `plan.md` + `requirements.md`.
  **This is where most artifact inputs originate.**
- **Stage 2.5 RESOLVE** (`.cap-dev-pipe/resolve-questions.py`) — **the collect/ask point.** For each
  field flagged at POLISH, RESOLVE fills it in priority order: a **pre-provided answer**
  (`.cap-dev-pipe/design/question-answers.yaml`) → a catalog **default** → an interactive prompt.
  The resolved value lands in `.contextcore.yaml`. This is the unattended-run channel (pre-seed
  `question-answers.yaml`), so no artifact ships with a blank/guessed target.
- **Stage 3 VALIDATE** — strict settings check; the hard gate for any input marked *required* by the
  criticality matrix (FR-E1) that is still blank.
- **Stage 4 EXPORT** resolves the manifest into `onboarding-metadata.json` with per-artifact
  `parameter_sources`, `resolved_artifact_parameters`, and `expected_output_contracts`.

The generator reads only `onboarding-metadata.json`, which is a deterministic projection of the
manifest. **Therefore the manifest is the canonical input surface**, the plan/requirements docs are
its upstream source, and **POLISH (flag) → RESOLVE (collect) → VALIDATE (gate)** is the collection
pipeline that fills it.

---

## 3. Input Surface Catalog (what exists today)

Every artifact field already has a declared source path (`onboarding-metadata.artifact_types[t].parameter_sources`).
The table below is the authoritative map of **what the pipeline already consumes**:

| Artifact | Input fields | Manifest source path | Run-008 state |
|----------|-------------|----------------------|---------------|
| prometheus_rule (alerts) | alertSeverity, availabilityThreshold, latencyThreshold, latencyP50Threshold, throughput | `spec.business.criticality`, `spec.requirements.{availability,latencyP99,latencyP50,throughput}` | ✅ populated (HTTP RED only) |
| slo_definition | availability, latencyP99, errorBudget, throughput | `spec.requirements.*` | ✅ populated |
| dashboard | criticality, dashboardPlacement, datasources, risks | `spec.business.criticality`, `spec.observability.dashboardPlacement`, `spec.risks[]` | ✅ populated |
| service_monitor | metricsInterval, namespace | `spec.observability.metricsInterval` | ✅ populated |
| loki_rule | logSelectors, recordingRules, labelExtractors, logFormat | `manifest (target-based)`, `spec.observability.logLevel` | 🟡 logLevel ok; selectors/rules templated |
| notification_policy | alertChannels, owner, owners | `spec.observability.alertChannels`, `spec.business.owner`, `metadata.owners` | 🔴 owner=`contact`, alertChannels=`['#1-20','#16-','#34']` (malformed) |
| runbook | risks, escalationContacts | `spec.risks[]`, `metadata.owners` | 🔴 owners=example stub; no procedures field |
| capability_index | project_root, index_dir | manifest / convention | ✅ |
| dashboard domain panels / domain alerts | the 10 `manifest_declared` metrics | `instrumentation_hints.<svc>.metrics.manifest_declared` (from `semantic_conventions.metrics:*`) | 🔴 no per-metric threshold field exists |

**Other known input channels:**
- `plan.md` + `requirements.md` — upstream of Stage 2 INIT (drive the manifest bootstrap).
- `.contextcore.yaml` `spec` / `strategy` / `guidance` / `insights` — full author surface
  (see `MANIFEST_ONBOARDING_GUIDE.md` Steps 2–5: business context, requirements/SLOs, targets,
  risks, **observability overrides**, objectives, escalation).
- `pipeline.env` — pipeline-level config (project root, profile).
- CLI flags: `--portal`, `--skip-observability`, `--skip-polish`, `--profile`.
- `semantic_conventions.metrics:*` (beaver / contextcore) — the source of `manifest_declared`
  business-observability metrics; config-driven, not per-project authored.

---

## 4. Content Gap Inventory (what needs provisioning)

Two classes of gap:

### 4a. Existing fields holding placeholder / malformed values (fixable via setup/config)

| Symptom in artifact | Root manifest value (run-008) | Fix |
|---------------------|-------------------------------|-----|
| runbook `Owner: contact` | `spec.business.owner: "contact"` | Populate real owner |
| runbook escalation = example | `metadata.owners: [{team: contact, slack: "#alerts", email: team@example.com}]` | Populate real on-call team/contacts |
| notification `REPLACE_WITH_WEBHOOK_URL` | `spec.observability.alertChannels: ['#1-20','#16-','#34']` (malformed parse) + no receiver URL | Provide real receiver target(s) |
| loki `logFormat` generic | `spec.observability.logLevel: info` | ok; optionally enrich log selectors |

### 4b. No input surface exists yet (requires schema extension)

| Need | Why un-derivable | Status |
|------|------------------|--------|
| **Per-domain-metric alert thresholds** (cost, tokens/s, truncation rate, context-usage ratio, active sessions) | No defensible default; business-specific | Domain alerts ship as commented `> <THRESHOLD>` stubs (`alerted` coverage 0.077). **No manifest field exists.** |
| **Runbook incident procedures** (step-by-step response, diagnostics, known-failure playbooks) | Operational knowledge held by people/docs | Runbook scores 0.4 — missing `Overview`/`Risks`/`Procedures` markers. **No procedures input field.** |
| **Notification receiver targets** (webhook URL, PagerDuty key, Slack channel mapping) | Secret/environment-specific | Placeholder only. |
| **Loki recordingRules / labelExtractors** | Log-shape specific | Template defaults only. |
| **Per-service SLO overrides** (Tier-1 stricter availability/latency) | Service-specific; inherit project default otherwise | No `spec.requirements.perService` map. |
| **Error-budget policy** + **RTO/recovery target** | Derivable from availability (budget) / operational (RTO) | No `errorBudget` / `rto` field. |
| **`runbook_url` base** | Org-specific runbook host; generator emits `https://runbooks.example.com/...` | No `runbook_base_url` input. |
| **`dashboard_url` / UID scheme** | The alert annotation emits `/d/obs-{service}` but the rendered dashboard UID is `cc-obs-{service}` — an **internal skew** (broken handoff). | No `dashboard_uid_scheme` input; one value should drive both sides. |
| **Business KPI targets** (conversion, AOV, payment-success, GMV, LLM/infra cost budget, …) | Business-specific goals; per-role | No `spec.businessTargets` block (metrics named on roles but carry no targets). |

---

## 5. Requirements

### Group A — Setup/config: populate & validate existing manifest fields

- **FR-A1 — Author-facing required-fields checklist.** The manifest schema MUST mark the
  artifact-driving fields (`spec.business.owner`, `metadata.owners`, `spec.observability.alertChannels`,
  `spec.requirements.*`, `spec.risks[]`) with a **provisioning status** (`authored` |
  `placeholder` | `absent`). Stage 2 INIT MUST NOT emit sentinel placeholders (`contact`,
  `team@example.com`, `#1-20`) as if authored — it marks them `placeholder`.
- **FR-A2 — Placeholder/sentinel validation gate.** A validator MUST flag known sentinels
  (`REPLACE_WITH_*`, `contact`, `*@example.com`, `runbooks.example.com`, malformed channel tokens)
  wherever they reach a generated artifact, and downgrade that artifact's quality score. *(Closes the
  run-007 residual where notification_policy scored 1.0 despite `REPLACE_WITH_WEBHOOK_URL`.)*
  **Consumer-side already partly live (REQ-OAT-061, step C2):** the generator's bridge *actionability*
  check now scores a bridge artifact's **human half partial** when its `runbook_url`/`dashboard_url`
  points at an artifact not produced this run — i.e. it already detects the *broken handoff* a
  placeholder causes. This FR is the *producer-side* root fix: gather the real value so the check
  passes for real. When an input is absent, the generator MUST keep the placeholder **and record
  `classification_source: placeholder`** (mirrors the REQ-OAT-024 `inferred` path) so the gap is
  visible, not silently shipped.
- **FR-A3 — Global config defaults.** `pipeline.env` (or a sibling `observability.env`) MUST
  support project/org-wide defaults for receiver targets and escalation (e.g.
  `OBS_DEFAULT_WEBHOOK_URL`, `OBS_DEFAULT_ONCALL_TEAM`) used when the manifest does not override.

### Group B — Schema extension: inputs with no surface today

- **FR-B1 — Domain-metric alert thresholds.** Add an authorable map under
  `spec.observability.metricThresholds` keyed by metric name →
  `{operator, value, severity, for}` (e.g. `startd8_cost_total: {op: ">", value: 50, unit: usd_per_hour, severity: warning}`).
  When present, the generator emits a **live** alert; when absent, it emits the commented stub
  AND the `alerted` coverage score reflects the absence (no silent inflation).
- **FR-B2 — Runbook content inputs.** Add `spec.observability.runbook` accepting authored
  `overview`, `risks[]`, `procedures[]` (ordered steps), and `escalation`. The generator merges
  authored content over the templated skeleton; the completeness markers (`Overview`, `Risks`,
  `Procedures`, `Escalation`) are satisfied by authored input rather than guessed.
- **FR-B3 — Notification receivers.** Add `spec.observability.receivers[]`
  (`{name, type: webhook|pagerduty|slack, target, severities[]}`) so multi-tier routing
  (critical/warning/info) and a real target replace the single placeholder route.
- **FR-B4 — Document-sourced enrichment.** Permit a referenced source document (markdown) per
  artifact (e.g. `spec.observability.runbook.source: docs/runbooks/strtd8.md`) whose content is
  imported via the existing `document_importer` / `document_chunking` utilities at INIT/EXPORT.
- **FR-B5 — Per-service SLO overrides, error budget, RTO.** Add `spec.requirements.perService`
  (map `svc → {availability, latencyP99}`, Tier-1 stricter, inheriting the project default),
  `spec.requirements.errorBudget` (authored or derived from availability), and
  `spec.requirements.rto` (recovery target, feeds the runbook + incident SLO). *(From the catalog
  A6–A9; the generator reads A1–A4 today — extend it to consume these.)*
- **FR-B6 — Handoff-target inputs (close the UID skew).** Add `spec.observability.runbook_base_url`
  (so `runbook_url = {base}/{service}/{alert}` instead of `runbooks.example.com`) and
  `spec.observability.dashboard_uid_scheme` (default `cc-obs-{service}`). The scheme MUST drive
  **both** the alert annotation `dashboard_url` **and** the rendered dashboard UID, eliminating the
  current `obs-`/`cc-obs-` mismatch so the REQ-OAT-061 actionability check can later resolve by exact
  UID, not just service granularity.

### Group C — Polish-stage supplemental input surface

- **FR-C1 — `observability-inputs.yaml` (per-run polish input).** The pipeline MUST accept an
  optional `--obs-inputs <file>` whose content is **merged into the manifest at/just-after Stage 1
  POLISH** (before INIT/EXPORT), at a precedence tier **below** authored manifest fields but
  **above** templated defaults. Shape mirrors the `spec.observability` extensions in Group B,
  keyed by service. This lets humans supply per-run content without editing the canonical manifest.
- **FR-C2 — Polish gate extends to observability inputs.** Stage 1 POLISH MUST add checks that
  report, per service: which artifact-driving fields are `authored` vs `placeholder`/`absent`,
  and surface the resulting expected `alerted` / runbook-completeness impact **before**
  generation — turning today's silent placeholders into a pre-flight report.
- **FR-C3 — Non-fatal by default.** Missing supplemental inputs MUST degrade gracefully (the
  artifact is still generated with templated content + honest low scores), consistent with the
  existing graceful-degradation requirement. Inputs improve output; they are not a hard gate
  unless explicitly configured (`--require-obs-inputs`).

### Group D — Provenance & feedback

- **FR-D1 — Input provenance.** Each generated artifact's derivation header MUST record whether
  each field was `authored` (manifest), `supplemental` (polish input), `config-default`, or
  `templated`, so reviewers can see what was human-provided vs guessed.
- **FR-D2 — Coverage of human inputs.** Extend the quality report with an
  `input_provisioning_score` per artifact (= authored-or-supplemented fields ÷ fields the
  contract declares), distinct from structural and metric-coverage scores.

### Group E — Business KPI / role-portal targets (business-observability inputs)

The per-role portal panels and business SLOs need **targets**, not just metric names. Today
`roles.yaml` lists `business_kpis` (the *metrics*) but carries **no targets**, so portals render
without goal lines and business SLOs aren't declared. (See §6b for the full catalog.)

- **FR-E1 — Required-by-criticality matrix.** Define which catalogued inputs are *mandatory* at each
  criticality (e.g. `critical/high` ⇒ availability + latency + error-budget + per-service Tier-1
  overrides required; `medium` ⇒ availability only). This matrix drives what POLISH flags (FR-C2)
  and what VALIDATE hard-gates (Stage 3). A `high` project with no availability target, or a role
  with a `business_kpis` entry but no matching `businessTargets` value, MUST be flagged — never
  silently defaulted.
- **FR-E2 — `spec.businessTargets` block.** Add an authorable map for business goals feeding role
  portals + business SLOs: `conversion_rate`, `average_order_value`, `revenue_goal`,
  `payment_success_rate` (also a business SLO), `gross_margin`, `infra_cost_budget`,
  `llm_cost_budget` (→ `startd8.cost.total`), and the rest of the §6b catalog. Targets are collected
  **now even when the live business metric isn't instrumented yet** — dashboards render goal
  lines / threshold bands and the SLO is declared (intent-first).
- **FR-E3 — Per-role framing (optional).** `roles.yaml` MAY carry a `top_goal` string per role
  (e.g. `"Lift checkout conversion to 2.5%"`) for the role-portal header.
- **FR-E4 — KPI↔target consistency guard.** VALIDATE MUST assert every `roles.yaml` role with a
  `business_kpis` entry has a matching `businessTargets` value, preventing goal-less KPI panels.

| Channel | Mechanism | Feeds | Authored by |
|---------|-----------|-------|-------------|
| **Manifest** `.contextcore.yaml` | `spec`/`strategy`/`guidance`/`insights` | all artifact params (canonical) | human (or INIT bootstrap) |
| Plan / requirements docs | `plan.md`, `requirements.md` | Stage 2 INIT manifest bootstrap | human |
| **Observability overrides** | `spec.observability.*` (sampling, interval, alertChannels, dashboardPlacement, logLevel, + proposed metricThresholds/runbook/receivers) | alerts, dashboards, loki, notification, runbook | human |
| Business observability metrics | `semantic_conventions.metrics:beaver|contextcore` → `instrumentation_hints.manifest_declared` | domain panels & (proposed) domain alerts | platform config |
| Risks | `spec.risks[]` | runbook, dashboard | human |
| Owners / escalation | `metadata.owners`, `spec.business.owner` | runbook, notification | human |
| SLO targets | `spec.requirements.*` | SLO, alerts | human |
| Global config | `pipeline.env` / proposed `observability.env` | receiver/escalation defaults | platform |
| Polish supplemental | proposed `observability-inputs.yaml` via `--obs-inputs` | per-run human content | human |
| Source documents | proposed `*.source:` refs → `document_importer` | runbook/portal prose | human/docs |
| CLI flags | `--portal`, `--skip-observability`, `--profile` | which artifacts/format | operator |

---

## 6b. Business KPI / role-portal target catalog (Group E reference)

Each names a *metric* (often already on a role) **plus a target** (the new input). Targets power
role-portal gauges/goal-lines and business SLOs. Most are blocked on business-metric
instrumentation for *live data*, but the **targets are collected now** so panels render goal lines
and SLOs are declared.

| # | Target | Unit | Example | Feeds | Source metric | Status |
|---|--------|------|---------|-------|---------------|--------|
| B1 | conversion rate | percent | `2.5%` | marketing portal; business SLO | `app_checkout_completed/sessions` | 🆕 |
| B2 | cart-abandonment | percent | `65%` | marketing portal | `app_cart_abandoned/started` | 🆕 |
| B3 | ad click-through | percent | `1.0%` | marketing portal | `ad_clicks/ad_impressions` | 🆕 |
| B4 | campaign ROAS | ratio | `4.0` | marketing portal | revenue/ad-spend | 🆕 |
| B5 | average order value | currency | `$85` | finance portal | `app_order_value_usd` | 🆕 |
| B6 | revenue goal (GMV) | currency/period | `$1.0M/mo` | finance portal | `sum(app_order_value_usd)` | 🆕 |
| B7 | payment success-rate | percent | `99.0%` | finance + SRE **business SLO** | `app_payments_total{status}` | 🆕 |
| B8 | gross-margin | percent | `40%` | finance portal | revenue − COGS | 🆕 |
| B9 | infra cost budget | currency/period | `$5k/mo` | finance cost panel | cloud billing | 🆕 |
| B10 | LLM cost budget | currency/period | `$500/mo` | finance/data-ml cost | `startd8.cost.total` | 🆕 |
| B11 | recommendation CTR | percent | `5%` | data-ml experiment loop | rec clicks/impressions | 🆕 |
| B12 | AOV uplift | percent | `+10%` | data-ml experiment loop | A/B vs baseline AOV | 🆕 |

**Proposed schema (additive, RESOLVE-collectable):**

```yaml
# .contextcore.yaml
spec:
  requirements:
    errorBudget: "0.1%"                 # FR-B5 (or derive from availability)
    rto: "15m"                          # FR-B5
    perService:                         # FR-B5 — Tier-1 overrides
      checkoutservice: {availability: "99.95", latencyP99: "300ms"}
      paymentservice:  {availability: "99.95", latencyP99: "250ms"}
  observability:
    runbook_base_url: "https://runbooks.acme.io"   # FR-B6
    dashboard_uid_scheme: "cc-obs-{service}"        # FR-B6 (drives annotation + render)
    receivers:                                       # FR-B3
      - {name: slack-sre, type: slack, target: "https://hooks.slack.com/…", severities: [critical, warning]}
    metricThresholds:                                # FR-B1
      startd8_cost_total: {op: ">", value: 500, unit: usd_per_month, severity: warning}
  businessTargets:                                   # FR-E2 — feeds role portals + business SLOs
    conversion_rate: "2.5%"
    average_order_value: "85 USD"
    payment_success_rate: "99.0%"      # also a business SLO
    llm_cost_budget: "500 USD/month"
```

---

## 7. Non-Goals

- Does **not** change the deterministic, $0 generation model — inputs are structured data /
  imported documents, not new LLM calls.
- Does **not** make inputs mandatory by default (graceful degradation preserved; FR-C3).
- Does **not** re-open the run-007 scoring findings (those are closed) — this builds on them by
  scoring **input provisioning** as a distinct dimension.
- Does **not** manage secrets storage — receiver targets reference env/secret indirection, not
  inline secrets.

---

## 8. Acceptance Snapshot (using strtd8)

A run with provisioned inputs MUST show, relative to run-008:
- `notification_policy`: real receiver, no `REPLACE_WITH_*`, sentinel validator green.
- `runbook`: `Overview`/`Risks`/`Procedures`/`Escalation` markers satisfied from authored input
  (score ≥ 0.8, up from 0.4).
- domain alerts: live rules for any metric with a `metricThresholds` entry; `alerted` coverage
  rises above 0.077 proportionally.
- `metadata.owners` / `spec.business.owner`: real values; runbook no longer prints `Owner: contact`.
- new `input_provisioning_score` present per artifact.
- bridge artifacts no longer score human-half partial for a placeholder `runbook_url`/`dashboard_url`
  (REQ-OAT-061), because `runbook_base_url`/`dashboard_uid_scheme` resolve to produced targets.

---

## 9. Open Questions

1. **Required-by-criticality matrix (FR-E1).** Exact mandatory set per criticality — e.g. `critical` ⇒
   availability + latency + error-budget + Tier-1 per-service overrides; `medium` ⇒ availability only.
   Defines precisely what POLISH flags and VALIDATE gates.
2. **Targets without instrumentation.** Collect B-series business targets now (goal lines) even though
   the live business metrics aren't emitted yet? *(Recommend yes — declare intent early; the SLO/goal
   line is valid before the series exists.)*
3. **Per-role vs per-service scoping.** Business targets are role-scoped; SLOs are service-scoped.
   Where does a business SLO like payment-success-rate live — `businessTargets` (role view) or
   `perService.payment` (service view)? Needs one home + a projection.
4. **Receiver/runbook secret indirection.** `receivers[].target` and `runbook_base_url` reference
   env/secret indirection (not inline secrets, per Non-Goals) — confirm the indirection mechanism
   (`OBS_DEFAULT_WEBHOOK_URL` env, FR-A3) vs per-service override precedence.
