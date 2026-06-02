# Polish-Stage Observability Input Collection — Requirements

**Version:** 0.3 (Second reflective pass — cross-repo grounding)
**Date:** 2026-06-02
**Status:** Draft
**Source:** Formalizes `OBSERVABILITY_POLISH_STAGE_INPUT_CATALOG.md` (the 148-input discovery sweep).
v0.2 planned against `artifact_generator.py`; v0.3 grounds against the cap-dev-pipe + ContextCore
contracts (`cap-dev-pipe/design/pipeline-requirements.md`, `POLISH_INPUT_GATHERING_BACKGROUND.md`),
which **reshaped ownership** and narrowed startd8's scope to a single change.
**Paired plan:** `OBSERVABILITY_POLISH_INPUT_PLAN.md`.

---

## 0. Planning Insights (Self-Reflective Update)

> Planning against `artifact_generator.py:load_business_context` (~line 555) changed the shape of this
> spec substantially — the generator already does more than the catalog assumed, which **narrows**
> scope.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| Need to build a "single source of intent" surface | The generator **already reads a per-project manifest `spec`**: `spec.business` (criticality, owner), **`spec.requirements` (availability, latencyP99, throughput, errorBudget)**, `spec.observability` (dashboardPlacement), `spec.project`, and `strategy.objectives[].keyResults[].window` | FR-1 is mostly **done** — the "one place" is the manifest `spec`. The real work is the **unread** fields (delivery), not a new surface |
| The $50 SLO / $100 alert split is the per-project cost goal to reconcile | Those live in **startd8's OWN self-manifest** (`docs/capability-index/startd8.observability.manifest.yaml` `slo_templates`/`alert_templates`) — which has **no `spec` block**. They monitor **startd8 itself** (cat-5 agent-obs), NOT the generated per-project service | OQ-1 reframed: the $50/$100 reconciliation is a small **SDK-self-monitoring** cleanup, *separate* from per-project polish-input collection. Don't conflate them |
| SLO goals (uptime/latency) need wiring | `spec.requirements.availability/latencyP99/throughput/errorBudget` already thread into SLOs/alerts/dashboards; error-budget already derives from availability (`1 − target`, :1337) | FR-5 collapses to "collect into `spec.requirements`" (already consumed) + derive — not new generator code |
| All gaps are equal | The genuinely **unread** operator inputs are exactly 3 delivery fields (webhook, runbook base, datasource) — they have **no manifest field and emit placeholders/constants**. The SLO goals are read; the operational knobs (query window, weights, scrape interval) are SDK-internal tuning, not per-project intent | Scope narrows to: **add `spec.delivery` (webhook/runbook/datasource) + wire it in**; everything else is "document the existing `spec.requirements` fields + collect into them" |

**Resolved open questions:**
- **OQ-5 → the manifest `spec` IS the read surface** (per-project manifest via `--manifest`). FR-1's
  "one place" already exists for goals; only delivery fields are missing.
- **OQ-4 → `spec.delivery` schema:** `{ webhook: {critical, warning} | url, runbook_base, datasource }`,
  read in `generate_notification_policy` (:1671), the runbook-URL annotation (:820), and the dashboard
  datasource (:1007). Mirrors how `spec.business`/`spec.requirements` are already read.
- **OQ-1 → keep separate:** per-project cost goal goes in `spec.requirements`; the startd8-self
  $50/$100 reconciliation is a separate one-line fix to the committed self-manifest, not part of polish
  collection.
- **OQ-3 → collect into the manifest `spec`** (the existing read surface). The "earliest polish stage"
  attaches by producing/augmenting the per-project manifest *before* `generate_observability_artifacts`
  runs; the mechanism (prompt vs `polish-inputs.yaml`) is a thin writer over the manifest, not a new
  generator input path.
- **OQ-2 → narrow:** close the **3 unread delivery fields** + document the already-read `spec.requirements`
  goals this pass; defer operational tuning (query window, weights, scrape interval) and the
  SDK-self-template reconciliation to follow-ups.

### 0.2 Second reflective pass (v0.2 → v0.3): cross-repo grounding

> v0.2 planned startd8 in isolation and proposed a new `spec.delivery` block. Grounding against the
> cap-dev-pipe + ContextCore contracts **invalidated that** and revealed a three-repo ownership split.

| v0.2 Assumption | Cross-repo Discovery | Impact |
|-----------------|----------------------|--------|
| startd8 adds a `spec.delivery` block for webhook/runbook/datasource | The manifest **schema is ContextCore-owned** and **already models the inputs**: `spec.observability.alertChannels` (REQ-CDP-OBS-005, naming-validated), `metadata.owners`, `spec.targets[]`, `spec.observability.metricsInterval/logLevel/dashboardPlacement`, `spec.requirements.*`, `spec.business.criticality`, `spec.risks[]` | **RETRACT `spec.delivery`.** Adding fields from startd8/cap-dev-pipe = a second source of truth for a schema we don't own. Any *new* field is a ContextCore ask |
| Polish writes/augments the manifest `spec` | **POLISH (Stage 1) runs BEFORE `init-from-plan` (Stage 2)** — at polish time **no manifest exists**. The spec is derived later from the plan | The "collect at polish" flow is **gather-at-polish → apply-at-init**, owned by **cap-dev-pipe**; there's already a Stage 2.5 RESOLVE-QUESTIONS surface (`question-answers.yaml` / `manifest fix --interactive`) to reuse, gated by REQ-CDP-INT-010 |
| The unread fields just need a generator wire-up + a new schema | **Verified:** `artifact_generator.py` reads `spec.observability.dashboardPlacement` + `spec.requirements` + `spec.business.criticality` only — it does **NOT** read `alertChannels`, `metadata.owners`, `spec.targets[]`, or `metricsInterval`, and emits placeholders for them | startd8's gap is **narrow and real**: consume the **existing** ContextCore manifest fields instead of placeholders/hardcoded values. No new schema |
| Validation (ranges, naming, consistency) is part of this spec | cap-dev-pipe **already requires** it: semantic plausibility of owners/channels (REQ-CDP-INT-002), channel naming conventions (REQ-CDP-OBS-005), availability ≥95% bound (their CRP R1-F1), required/optional parameter classification (REQ-CDP-INT-007) | **RE-HOME validation** to cap-dev-pipe/ContextCore; startd8 trusts validated manifest values |

**Resolved (this pass):**
- **OQ-6 → resolved.** `alertChannels` are channel *identifiers* (naming-validated), not webhook URL
  transport. Per-project input = the channel(s) (`spec.observability.alertChannels`, exists); the
  webhook/contact-point *endpoint* is environment config (like `GRAFANA_API_TOKEN`), not per-project.
  So the generator routes by `alertChannels`; no severity→URL map is authored per project.
- **OQ-7 → resolved.** cap-dev-pipe DOES emit `.contextcore.yaml` `spec:` — at **Stage 2**, authored
  by ContextCore, **after** polish. Gather-at-polish/apply-at-init; reuse Stage 2.5 plumbing; do not
  hand-edit the manifest.

**New (this pass):**
- **OQ-8 (ContextCore).** Is there a manifest home for the **runbook URL base** and the **datasource
  name**? The innate OBS reqs model `alertChannels`/`owners`/`targets`/`metricsInterval` but **not** a
  runbook base or datasource. Either ContextCore adds fields (e.g. `spec.observability.runbookBase`,
  `…datasource`) or startd8 treats them as environment/config defaults. **Decision needed before
  implementation** (drives FR-CONS-2/3).

---

## 1. Problem Statement

Observability artifact generation (`artifact_generator.py` → alerts, dashboards, SLOs, notification
policies, runbooks, service monitors) consumes **operator-intent inputs** — uptime goals, latency
targets, cost budgets, alert thresholds, webhook URLs, runbook links — but today those inputs are
either edited into a manifest YAML *after* generation, or **hardcoded**, including two literals that
**ship broken**:

| Component | Current state | Gap |
|-----------|--------------|-----|
| Alert webhook URL | `"REPLACE_WITH_WEBHOOK_URL"` placeholder (artifact_generator.py:1671) | Generated notification policy is non-functional until hand-edited |
| Runbook URL base | `https://runbooks.example.com/...` placeholder (:820) | Every alert links to a dead domain |
| Prometheus datasource | hardcoded `"prometheus"` (:1007) | Dashboards break if the target Grafana names it differently |
| SLO/alert goals (uptime, latency, budget) | manifest templates, edited post-gen | Operator intent collected late, not at polish entry |
| Cost goal | SLO target **$50/day** vs budget alert **$100/day** — inconsistent | Two unreconciled numbers for one intent |
| Alert for-durations, query window, scrape interval, quality weights | hardcoded | Operational tuning needs a code change |

The polish stage should **collect operator intent up front** and thread it into generation, so
artifacts are correct on first emit.

## 2. Requirements

The v0.2 collection/schema requirements were re-homed (see §0.2). What remains for **startd8** is one
focused change: **consume the manifest delivery fields ContextCore already populates, instead of
emitting placeholders.** The gather flow, schema, and validation are delegated (§2.2).

### 2.1 startd8 consumption requirements (the actual work)

**FR-CONS-1 (consume existing delivery fields).** `artifact_generator.py` MUST read these
already-populated, ContextCore-owned manifest fields and thread them into the named artifacts,
replacing today's placeholders/hardcoded values:
- `spec.observability.alertChannels` → `notification_policy` routing (REQ-CDP-OBS-005) — replaces
  `REPLACE_WITH_WEBHOOK_URL` (:1671); route by channel identifier, severity-mapped via the existing
  `_CRITICALITY_TO_SEVERITY`.
- `metadata.owners` → `notification_policy` owner + `runbook` escalation contacts (REQ-CDP-OBS-005/007)
  — replaces the missing/`TODO` owner.
- `spec.targets[]` (`.name`, `.namespace`) → `service_monitor` selector/namespace + `loki_rule`
  selector + dashboard target (REQ-CDP-OBS-004/006) — replaces the `app={service_id}` / fixed-namespace
  assumptions.
- `spec.observability.metricsInterval` → `service_monitor` scrape interval (REQ-CDP-OBS-004) — replaces
  hardcoded `"30s"` (:1606).

**FR-CONS-2 (runbook base).** The runbook URL base MUST stop being the `runbooks.example.com`
placeholder (:820). Source per OQ-8: read a manifest field if ContextCore adds one, else a
config/env default (`OBS_RUNBOOK_BASE`), else omit the annotation rather than emit a dead domain.

**FR-CONS-3 (datasource).** The Prometheus datasource name (:1007) MUST be configurable (env/config
default `"prometheus"`), per OQ-8; not a hardcoded literal.

**FR-CONS-4 (backward-compatible, parameter-classification-aware).** With a field absent, the generator
MUST fall back to today's default and MUST NOT emit a dead placeholder for a *required* delivery
parameter — instead honor REQ-CDP-INT-007: a missing **required** parameter (e.g. `alertChannels` for
`notification_policy`) is surfaced as unresolved (Gate-1 visible), a missing **optional** one defaults
silently. No manifest field becomes mandatory to run; absent-everything output stays byte-identical to
today except the placeholders are no longer fabricated.

### 2.2 Delegated — NOT startd8 (cross-references)

- **Polish-stage input gathering** (show helpful inputs, collect, apply) → **cap-dev-pipe**:
  gather-at-polish → apply-at-`init-from-plan`, reusing Stage 2.5 RESOLVE-QUESTIONS /
  `question-answers.yaml` / `manifest fix --interactive`, gated by REQ-CDP-INT-010. See
  `POLISH_INPUT_GATHERING_BACKGROUND.md` §5.
- **Manifest schema (any new field)** → **ContextCore** (`manifest init-from-plan`). Includes the OQ-8
  decision on `runbookBase`/`datasource` fields.
- **Input validation** (ranges, channel naming, owner semantic plausibility, availability bounds) →
  **cap-dev-pipe/ContextCore**: REQ-CDP-INT-002, REQ-CDP-OBS-005, REQ-CDP-INT-007. startd8 trusts
  validated manifest values.
- **startd8-self `$50/$100` reconciliation** → a separate one-line fix to the committed self-manifest
  (`startd8.observability.manifest.yaml`), tracked independently.

## 3. Non-Requirements / out of scope

- NOT adding a `spec.delivery` block or any manifest field (schema is ContextCore's — §2.2).
- NOT building an input-collection/prompt surface (cap-dev-pipe's, and it already exists — §2.2).
- NOT validating input plausibility (cap-dev-pipe/ContextCore's, per REQ-CDP-INT-002 — §2.2).
- NOT changing artifact output *formats*, only the *values* threaded in.
- NOT a Grafana-credentials manager (API token stays env `GRAFANA_API_TOKEN`).
- NOT the `route_state`/taxonomy generator work (separate cat-4/5 Task C).
- NOT the operational tuning knobs (query window, for-durations, quality weights) — SDK-internal,
  deferred.

## 4. Open Questions

OQ-1..5 resolved in §0 (v0.2 planning); OQ-6/7 resolved in §0.2 (cross-repo grounding). One live:

- **OQ-8 (live — needs a decision before implementation).** Manifest home for **runbook URL base** and
  **datasource name**: does ContextCore add `spec.observability.runbookBase` / `…datasource`, or does
  startd8 treat them as env/config defaults? Drives FR-CONS-2/3. (Recommendation: env/config defaults
  now; propose ContextCore fields if they become per-project intent.)

---

*v0.3 — Second reflective pass (cross-repo grounding). Retracted the `spec.delivery` block and the
collection/validation FRs after grounding against cap-dev-pipe + ContextCore: the manifest schema is
ContextCore-owned and already models the inputs; the gather flow is cap-dev-pipe's (already specced);
polish runs before the manifest exists. startd8's scope collapsed to **FR-CONS-1..4 — consume the
existing manifest delivery fields (`alertChannels`/`owners`/`targets`/`metricsInterval`) instead of
emitting placeholders.** 8 OQs resolved, 1 live (OQ-8, runbook-base/datasource home). Paired plan:
`OBSERVABILITY_POLISH_INPUT_PLAN.md`.*
