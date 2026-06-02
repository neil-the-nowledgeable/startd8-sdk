# Polish-Stage Observability Input Collection — Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-02
**Status:** Draft
**Source:** Formalizes `OBSERVABILITY_POLISH_STAGE_INPUT_CATALOG.md` (the 148-input discovery sweep)
into a buildable spec. Planning pass examined `artifact_generator.py`'s actual input-read sites.

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

**FR-1 (single source of intent — surface already exists).** Operator-intent inputs MUST be collected
into the per-project manifest `spec`, which the generator **already reads** (`spec.business`,
`spec.requirements`, `spec.observability`, `spec.project`, `strategy`). This requirement is therefore
satisfied for goals **today**; the only addition is a new **`spec.delivery`** block for the unread
delivery fields (FR-2/3/4). No operator-facing input may remain a code constant or a generated
placeholder.

**FR-2 (alert delivery — webhook).** The alert webhook target(s) MUST be a collected input, routable
by severity (e.g. critical→page, warning→Slack), threaded into the generated `notification_policy`.
The `REPLACE_WITH_WEBHOOK_URL` placeholder MUST NOT appear in a generated artifact when an input is
provided.

**FR-3 (runbook + contact).** The runbook URL base and on-call owner/contact MUST be collected inputs,
replacing the `runbooks.example.com` placeholder in alert annotations + runbooks.

**FR-4 (datasource).** The Prometheus datasource name MUST be a collected input (default `"prometheus"`).

**FR-5 (SLO goals, collected once — into the existing `spec.requirements`).** Uptime/availability,
latency objective, and (per-project) cost budget MUST be collected into `spec.requirements`
(`availability`, `latencyP99`, `throughput`, `errorBudget`) — the fields the generator already
consumes. Error-budget already derives from availability (`1 − target`, artifact_generator.py:1337);
collection MUST NOT re-author it. The startd8-self `$50/$100` template split is a **separate**
SDK-self-monitoring fix (see §0 / OQ-1), not part of per-project collection.

**FR-6 (alert thresholds + timing).** Truncation-rate, context-saturation, budget, and latency alert
thresholds + their `for_duration` MUST be collectable inputs (defaulting to today's template values).

**FR-7 (operational tuning — scoped).** Query rate window (`[5m]`), scrape interval (`30s`), and
quality weights (0.7/0.3) MAY be exposed as advanced inputs; default to current constants. (Lower
priority — see OQ-2.)

**FR-8 (collection mechanism).** Inputs MUST be collectable at the EARLIEST polish stage via a single
mechanism (prompt and/or `polish-inputs.yaml`) and persisted into the manifest before generation runs.
(See OQ-3.)

**FR-9 (backward-compatible defaults).** Every input MUST default to today's value; with no inputs
provided, generation MUST produce byte-identical artifacts to today (except the placeholders, which
remain placeholders only when truly unset). No input is mandatory to run.

**FR-10 (validation at collection).** Collected inputs MUST be validated at collection time: ranges
(0–1 fractions, positive durations/budgets), URL/webhook format, and **goal consistency** (budget
alert ≥ SLO budget; error-budget = 1 − availability).

## 3. Non-Requirements / out of scope

- NOT building a new generator or changing artifact output *formats* (only their input values).
- NOT exposing Tier-5 internal knobs with no operator meaning (panel grid geometry, manifest IDs,
  jsonnet timeout, capability maturity literal).
- NOT a Grafana-credentials manager (the API token stays an env var, `GRAFANA_API_TOKEN`).
- NOT changing the `route_state`/taxonomy generator work (that's the separate cat-4/5 Task C).

## 4. Open Questions

**All v0.1 open questions resolved by the planning pass — see §0 Planning Insights.**
- OQ-1 → keep per-project (`spec.requirements`) and SDK-self (`$50/$100` templates) cost goals
  **separate**; reconcile the self-templates as a follow-up.
- OQ-2 → **narrow** to the 3 unread delivery fields + document the already-read goals.
- OQ-3 → collect into the manifest `spec` (existing read surface); polish writer is thin.
- OQ-4 → `spec.delivery = { webhook, runbook_base, datasource }`, read at :1671/:820/:1007.
- OQ-5 → yes, the generator reads the per-project manifest `spec` today.

**New (post-planning):**
- **OQ-6.** Webhook shape: a severity→URL map (`{critical, warning}`) vs a single URL + Alertmanager
  routing? (Planning leans severity-map, mirroring `_CRITICALITY_TO_SEVERITY`.)
- **OQ-7.** Does cap-dev-pipe already emit a per-project manifest with a `spec` block at an earlier
  stage that the polish writer should augment, or does polish create it? (Determines writer vs
  augmenter.)

---

*v0.2 — Post-planning self-reflective update. The generator already reads the manifest `spec`, so
FR-1 is largely satisfied and scope narrows to a `spec.delivery` block (3 unread fields) + documenting
the existing `spec.requirements` goals; the $50/$100 split was reframed as a separate SDK-self fix.
5 OQs resolved, 2 added. Ready for an implementation plan (the unread-fields wiring is small) or an
optional CRP pass.*
