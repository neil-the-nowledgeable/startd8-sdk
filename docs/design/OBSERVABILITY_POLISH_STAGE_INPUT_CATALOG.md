# Observability Artifact Generation — Polish-Stage Input Catalog

**Date:** 2026-05-31
**Purpose:** Identify every **number, field, threshold, target, URL, and webhook** that is an
*input* to a generated observability artifact (dashboards, SLIs, SLOs, alerts, notification
policies, runbooks, service monitors), document **what it is and how it's used**, and recommend
which to **surface at the EARLIEST stage of cap-dev-pipe's polish stage** rather than leave hardcoded
or discovered late.

> **The problem this solves.** Today an operator's *intent* — "we want 99.9% uptime," "page us at
> $100/day," "send alerts to this Slack webhook" — is either (a) buried in a manifest YAML that's
> edited after generation, or (b) **hardcoded** (placeholder webhook URL, example.com runbook base,
> `5m` for-durations, quality weights). The polish stage should **collect the goals up front** and
> thread them into generation, so the artifacts are *correct on first emit*, not stubbed.

Grounded by a full sweep (148 inputs across 15 categories); this doc curates the **operator-facing**
subset and the **highest-value gaps**. File:line anchors are to `src/startd8/observability/` and
`docs/capability-index/startd8.observability.manifest.yaml` unless noted.

---

## How the polish stage should use this

1. **Collect Tier 1–3 inputs first** (goals, thresholds, delivery) — these encode operator intent and
   change per project. Prompt for them at polish entry; default to the values below.
2. **Thread them into generation** via the manifest `spec.business`/`slo_templates`/`alert_templates`
   and the CLI flags — most Tier 1 already have a manifest home; the **gaps** (§Gaps) are hardcoded
   and need a config surface added.
3. **Tier 4–5 are environment/tuning** — collect once per environment (Grafana URL, token), not per
   project.

A ⚙️ marks **already configurable** (just surface it in the prompt); 🔒 marks **hardcoded — needs a
new knob** (the polish-stage work).

---

## Tier 1 — GOALS & TARGETS (collect first; this is operator intent)

| Input | What it is / how used | Artifact(s) | Current default | Source |
|-------|----------------------|-------------|-----------------|--------|
| **Availability / uptime SLO** | The uptime goal (0–1). Used as the SLO objective AND derives the error-budget = `1 − target` for dashboard gauges + the availability alert | SLO, dashboard, alert | **0.99** (99%) | ⚙️ manifest `slo_templates[availability].target` (YAML:~690); 🔒 fallback `_DEFAULT_THRESHOLDS["availability"]="99"` (artifact_generator.py:148) |
| **SLO evaluation window** | Rolling lookback for the SLO (OpenSLO `timeWindow.duration`) | SLO | **30d** (availability), **7d** (latency) | ⚙️ manifest `slo_templates[].window` |
| **Latency objective (p95)** | Target p95 response time (ms) the SLO holds under | SLO, dashboard threshold | **5000 ms** | ⚙️ manifest `slo_templates[latency_p95].target` (YAML) |
| **Latency alert threshold (p99)** | p99 latency that fires an alert | alert, dashboard | **500 ms** | 🔒 `_DEFAULT_THRESHOLDS["latency_p99"]="500ms"` (artifact_generator.py:149) |
| **Daily cost SLO target** | Cost-per-day budget the SLO holds under (USD) | SLO | **$50/day** | ⚙️ manifest `slo_templates[cost_per_day].target` |
| **Throughput target** | Expected request rate baseline | alert, dashboard | **100 rps** | 🔒 `_DEFAULT_THRESHOLDS["throughput"]="100rps"` (artifact_generator.py:150) |

> ⚠️ **Reconcile-me:** the **cost_per_day SLO target ($50)** and the **budget_exceeded alert ($100)**
> are two different cost goals in the same manifest. The polish stage should collect **one** "daily
> cost budget" and derive both (e.g. SLO at the budget, alert at 1.5–2× as the page threshold), or
> explicitly collect both with the relationship made visible.

---

## Tier 2 — ALERT THRESHOLDS, TIMING & SEVERITY

| Input | What it is / how used | Artifact | Current default | Source |
|-------|----------------------|----------|-----------------|--------|
| **Truncation-rate alert** | Fraction of requests truncated before paging | alert | **> 0.10** (10%), for **5m** | ⚙️ manifest `alert_templates[high_truncation_rate].expr/for_duration` |
| **Context-saturation alert** | Context-window utilization that warns | alert | **> 0.90** (90%), for **2m** | ⚙️ manifest `alert_templates[context_near_capacity]` |
| **Budget-exceeded alert** | Daily cost that pages | alert | **> $100/day** (critical), for **1m** | ⚙️ manifest `alert_templates[budget_exceeded]` |
| **Convention alert for-durations** | How long a condition holds before firing (latency/error/availability alerts) | alert | 🔒 **"5m"** everywhere | 🔒 artifact_generator.py:728, 765, 801 |
| **Criticality → severity map** | Business criticality → Prom `severity` label (critical/high→critical, medium→warning, low→info) | alert, notification, runbook | 🔒 fixed map | 🔒 `_CRITICALITY_TO_SEVERITY` (artifact_generator.py:140–145) |
| **Service criticality** | The business-criticality input that drives the above | alert severity, dashboard tags, runbook escalation | **"medium"** | ⚙️ manifest `spec.business.criticality` |

---

## Tier 3 — DELIVERY & ROUTING (webhooks, contacts, links)

**These are the headline "webhook URL" items — currently placeholders/stubs that must become real
polish-stage inputs.**

| Input | What it is / how used | Artifact | Current value | Source |
|-------|----------------------|----------|---------------|--------|
| **Alert webhook URL** | The Slack/PagerDuty/email/webhook endpoint alerts route to | notification_policy | 🔒 **`"REPLACE_WITH_WEBHOOK_URL"`** stub | 🔒 artifact_generator.py:1671 (+ TODO line 1678) |
| **Runbook URL base** | Per-alert runbook link annotation operators follow on-call | alert, runbook | 🔒 **`https://runbooks.example.com/{service}/{alert}`** placeholder | 🔒 artifact_generator.py:820 |
| **On-call owner / contact** | Escalation target in the runbook | runbook | None → TODO placeholder | ⚙️ manifest `spec.business.owner` (artifact_generator.py:1782) |
| **Notification grouping** | `group_by`, `group_wait` (30s), `repeat_interval` (4h) — alert dedup/fatigue tuning | notification_policy | 🔒 hardcoded | 🔒 artifact_generator.py:1661–1663 |
| **Dashboard link base** | `/d/obs-{service}` link surfaced on alerts + runbooks | alert, runbook | derived | 🔒 pattern (artifact_generator.py:739, 1765) |

---

## Tier 4 — PROVISIONING & ENVIRONMENT (collect once per environment)

| Input | What it is / how used | Current | Source |
|-------|----------------------|---------|--------|
| **Grafana provision URL** | Target Grafana for dashboard upsert | ⚙️ `--provision` / `--portal-provision` (opt-in) | scripts/generate_observability_artifacts.py:102 |
| **Grafana API token** | Auth secret for provisioning | ⚙️ env `GRAFANA_API_TOKEN` | dashboard_creator/grafana_client.py:22 |
| **Prometheus datasource name** | Datasource the dashboards query | 🔒 **"prometheus"** | 🔒 artifact_generator.py:1007 |
| **Dashboard UID convention** | `obs-{service}` / `cc-portal-{project}` (idempotent upsert; `enforce_uid=false`) | 🔒 pattern | 🔒 artifact_generator.py:1001, portal_spec_builder.py:132 |
| **Scrape interval** | ServiceMonitor scrape period | 🔒 **"30s"** | 🔒 artifact_generator.py:1606 |
| **Metrics port / path** | ServiceMonitor endpoint (`metrics` / `/metrics`) | 🔒 fixed | 🔒 artifact_generator.py:1620 |
| **Grafana min version / timeouts** | v9+; connect 10s / request 30s | 🔒 fixed | 🔒 grafana_client.py:19–21 |

---

## Tier 5 — GENERATION GATES & TUNING (quality knobs)

| Input | What it is / how used | Current | Source |
|-------|----------------------|---------|--------|
| **Min metric coverage** | Fail the run if semantic metric-coverage < X | ⚙️ `--min-metric-coverage` (opt-in) | scripts:110 |
| **Min artifact-type coverage** | Fail if artifact-type coverage < X | ⚙️ `--min-artifact-type-coverage` | scripts:120 |
| **Quality weights** | Composite score = structural **0.7** + coverage **0.3**; per-service dash/alert/slo **0.35/0.35/0.30** | 🔒 hardcoded | 🔒 artifact_generator.py:356–357; validators/observability_artifact_checks.py:641,661 |
| **Query rate window** | `[5m]` in every PromQL rate()/histogram (alerts, SLOs, dashboards) — appears 15+ places | 🔒 **"[5m]"** | 🔒 artifact_generator.py:725+ |
| **Latency quantiles** | Which percentiles panels show (p50/p95/p99) | 🔒 0.50/0.95/0.99 | 🔒 artifact_generator.py:371, 947 |
| **Budget warning threshold** | Fraction of limit that warns (cost budget API) | ⚙️ **0.8** | costs/budget.py:82 |

---

## Recommended "earliest-polish" minimal input set

Collect these **6 goals** at polish entry (everything else can default):

1. **Uptime goal** (availability SLO target) — e.g. `0.999` → drives SLO + error-budget + availability alert
2. **Latency goal** (p95 ms, + p99 alert ms)
3. **Daily cost budget** (USD) — derive SLO target *and* the budget alert from one number (resolve the $50/$100 split)
4. **Alert webhook URL(s)** — by severity (critical→page, warning→Slack); replaces `REPLACE_WITH_WEBHOOK_URL`
5. **Runbook URL base + on-call owner** — replaces `runbooks.example.com`
6. **Service criticality** — drives severity routing

Plus, once per environment: **Grafana URL + API token + datasource name**.

---

## Gaps — hardcoded values that should become polish-stage knobs

🔒 **Highest value (operator intent, currently stubbed/baked):**
- **Webhook URL** (`REPLACE_WITH_WEBHOOK_URL`) and **runbook URL base** (`runbooks.example.com`) — the
  two literal placeholders that ship broken; must be polish inputs.
- **Convention alert for-durations** (`5m`), **query rate window** (`[5m]`), **scrape interval**
  (`30s`) — operational tuning currently uneditable without code changes.
- **Default thresholds** (availability 99 / latency 500ms / throughput 100rps) and **quality weights**
  (0.7/0.3, 0.35/0.35/0.30) — should be a central config, not constants in two modules.
- **Prometheus datasource name** (`"prometheus"`) — breaks if the target Grafana names it differently.

🪢 **Consistency to enforce at collection time:**
- Reconcile **cost_per_day SLO ($50)** vs **budget_exceeded alert ($100)** — collect one budget.
- Error-budget is derived from availability — collect availability once, don't let the alert and SLO
  drift.

**Suggested mechanism:** a single `polish-inputs.yaml` (or interactive prompt) collected at polish
entry, written into the manifest `spec.business` + `slo_templates`/`alert_templates` + a new
`spec.delivery` block (webhook/runbook/datasource), so generation reads operator intent from one
place and the placeholders never reach an artifact.

---

*Catalog v1.0 — operator-facing inputs to observability artifact generation, for cap-dev-pipe
polish-stage exposure. Full 148-input inventory available on request; this curates Tiers 1–5 and the
gaps. Values verified against `artifact_generator.py` + the committed manifest YAML on 2026-05-31.*
