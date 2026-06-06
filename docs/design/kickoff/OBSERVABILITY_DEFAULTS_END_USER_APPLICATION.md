# Observability Defaults — Industry Dataset: `end_user_application`

**Version:** 0.1
**Date:** 2026-06-05
**Status:** Draft — demo defaults (fictional budgets/contacts by design)
**Parent:** [`../OBSERVABILITY_INPUT_PROVISIONING_REQUIREMENTS.md`](../OBSERVABILITY_INPUT_PROVISIONING_REQUIREMENTS.md)
(Groups A–E input catalog) · [`../KICKOFF_REQUIREMENTS.md`](../KICKOFF_REQUIREMENTS.md) (FR-X
machinery) · [`../HITM_ROLE_MODEL_REQUIREMENTS.md`](../HITM_ROLE_MODEL_REQUIREMENTS.md) (tier
taxonomy — this dataset is tier-R-style reuse; the §3 list is tier E)
**Concept:** observability inputs for a demo do not need per-project human authoring — they come
from an **industry-specific default dataset** supplied by the startd8-sdk + ContextCore combined
process via cap-dev-pipe. This file is the first dataset: industry = **end-user application**.
Business-type inputs are NOT defaulted — they are handed to the humans as the §3 request list.

**Provenance rule (load-bearing):** every value below enters the manifest with provenance
**`config-default`** (FR-X4) — visible as a deliberate default in the pre-flight report, and
**never** sentinel-flagged (FR-A2 catches `*@example.com` / `REPLACE_WITH_*`; these defaults
deliberately use the reserved `.test` TLD and env-indirection instead, so an honest default is
distinguishable from an unfilled placeholder). A human override of any value flips it to
`authored`.

**Delivery mechanism:** the dataset ships as a manifest fragment (below) merged at Stage 2 INIT,
plus a pre-seeded `question-answers.yaml` entry set for any RESOLVE-collected fields — the
existing unattended channel; no new machinery.

---

## 1. The defaults (manifest-shaped, ready to merge)

```yaml
# industry-dataset: end_user_application (demo) — all values provenance: config-default
metadata:
  owners:
    - team: startdate-demo
      slack: "#startdate-alerts"
      email: ops@startdate.test          # RFC 2606 reserved TLD — fictional, NOT a sentinel
      oncall: startdate-primary

spec:
  business:
    criticality: medium                  # demo posture; raise to high for real launch
    owner: startdate-demo

  requirements:
    availability: "99.5"                 # end-user app demo baseline (~3.6 h/30 d budget)
    latencyP99: "500ms"                  # server-rendered HTMX page budget
    latencyP50: "150ms"
    trafficProfile: internal             # REQ-CDP-INT-003 lookup → throughput 100 rps
    errorBudget: "0.5%"                  # derived from availability (1 − target)
    rto: "1h"                            # demo recovery target
    perService:                          # Tier-1 stricter where user trust is on the line
      web: {availability: "99.5", latencyP99: "500ms"}
      auth: {availability: "99.9", latencyP99: "300ms"}
      ai_layer: {availability: "99.0", latencyP99: "8s"}   # LLM passes — latency budget is provider-bound

  observability:
    metricsInterval: "30s"
    logLevel: info
    logFormat: json
    dashboardPlacement: "ContextCore/StartDate"
    dashboard_uid_scheme: "cc-obs-{service}"               # FR-B6 — drives annotation AND render
    runbook_base_url: "https://runbooks.startdate.test"    # fictional org host (reserved TLD)
    alertChannels: ["#startdate-alerts"]
    receivers:                                             # FR-B3 — env-indirected, never inline
      - {name: slack-demo, type: slack, target: "${OBS_DEFAULT_WEBHOOK_URL}", severities: [critical, warning]}
    metricThresholds:                                      # FR-B1 — domain metrics get LIVE alerts
      startd8_cost_total:        {op: ">", value: 2,     unit: usd_per_day,  severity: warning,  for: 15m}
      startd8_cost_total_burst:  {op: ">", value: 5,     unit: usd_per_day,  severity: critical, for: 5m}
      startd8_truncation_rate:   {op: ">", value: 0.05,  unit: ratio,        severity: warning,  for: 15m}
      startd8_context_usage:     {op: ">", value: 0.85,  unit: ratio,        severity: warning,  for: 10m}
      startd8_tokens_per_minute: {op: ">", value: 50000, unit: tokens_min,   severity: info,     for: 30m}
      app_error_rate:            {op: ">", value: 0.02,  unit: ratio,        severity: critical, for: 5m}
      app_active_sessions:       {op: "<", value: 1,     unit: count,        severity: info,     for: 60m}  # demo heartbeat
    runbook:                                               # FR-B2 — generic end-user-app skeleton
      overview: >
        Server-rendered end-user web application (FastAPI + SQLModel + HTMX, SQLite/WAL) with an
        LLM enrichment layer. User-facing failure = page 5xx/slow render; backend failure = LLM
        pass errors, cost overrun, or DB lock contention.
      risks:
        - {type: availability, description: "SQLite write-lock contention under concurrent writes", mitigation: "WAL + busy_timeout are set by scaffold; check long transactions", priority: medium}
        - {type: cost, description: "LLM enrichment pass loops or oversized prompts", mitigation: "cost ceiling + startd8_cost_total alerts", priority: high}
        - {type: quality, description: "LLM provider degradation/truncation", mitigation: "truncation-rate alert; retry/fallback pass config", priority: medium}
      procedures:
        - "Triage from the cc-obs-{service} dashboard: error rate, p99, cost panel."
        - "5xx spike → check most recent deploy/regenerate; roll back the app process first."
        - "Slow renders → check DB lock waits (WAL busy), then LLM-pass latency."
        - "Cost alert → identify the AI pass via startd8.cost per-request attribution; pause the pass."
        - "LLM errors/truncations → check provider status; reduce prompt size or switch model tier."
      escalation: "oncall (startdate-primary) → team lead → provider support"

  risks: []   # project-specific entries are human-authored; runbook risks above are the industry defaults
```

**What this satisfies:** every 🔴/🟡 row of the provisioning doc's §3 run-008 table (owners,
receivers, thresholds, runbook content, handoff targets) now has an honest, non-sentinel default
— domain alerts emit **live** (FR-B1), the runbook scores its completeness markers from supplied
content (FR-B2), and the `obs-`/`cc-obs-` UID skew closes (FR-B6).

---

## 2. Fictional budgets (made up, demo-reasonable)

| Budget | Value | Where it lands |
|--------|-------|----------------|
| LLM cost budget | **$50 / month** (≈ the $2/day warning threshold above) | `businessTargets.llm_cost_budget` → `startd8.cost.total` panel + alert |
| Infra cost budget | **$100 / month** | `businessTargets.infra_cost_budget` (panel only — no live cloud-billing series in demo) |
| Pipeline run budget | **$5.00 / run** (the existing `--cost-budget` default, now *deliberate*: provenance `config-default` → `authored` when passed explicitly) | cap-dev-pipe `--cost-budget` |

---

## 3. Business inputs — request list for the StartDate team (tier E: human-authoritative)

These are **not defaulted** by the dataset — the team's decision is authoritative (tier E).
Per the 2026-06-05 operator decision (Q7), each ships **pre-filled with an LLM-drafted starter
value** (provenance `estimate` — FR-J6's default mode): the team approves or adjusts, never
fills blanks. Catalog adapted from §6b of the provisioning doc to the StartDate product
(value-pitch / candidate-profile app) — the team should rename metrics to match their KPIs; the
*shape* is what matters.

| # | Input the team provides | Unit / shape | **Starter value (LLM draft — approve/adjust)** | Why it's needed | Feeds |
|---|------------------------|--------------|------------------------------------------------|-----------------|-------|
| T1 | Profile-completion target | percent | **70%** of started profiles reach complete | the app's core funnel KPI — goal line on the completeness panel | role portal gauge; business SLO |
| T2 | Value-map / pitch generation success target | percent | **90%** of generation attempts yield an accepted artifact | "did the user get the artifact they came for" | portal; business SLO |
| T3 | Export/package usage target | ratio | **2** exports per active user per month | measures delivered value, not activity | finance/product panel |
| T4 | Active-users goal (weekly) | count | **25** weekly actives (demo scale) | demo traction line | portal goal line |
| T5 | Acceptable AI-pass cost per enriched profile | currency | **≤ $0.50** per profile (≈ 100 profiles/mo inside the $50 ceiling) | unit economics guardrail | cost panel threshold |
| T6 | Payment / conversion targets (if/when monetized) | percent, currency | **free during demo**; starter when monetized: 5% trial→paid, $15/mo | B1/B5/B7-class targets — only the team can set these | business SLOs |
| T7 | Per-role `top_goal` one-liner (FR-E3, optional) | string | e.g. *"Ship a pitch you'd actually send"* (candidate); *"Every profile reaches a complete value map"* (product) | role-portal headers | portals |
| T8 | Real owner/contact + escalation (replaces the §1 fictional `startdate.test` block at launch) | owners block | **no starter — human-only** (tier U: real contacts cannot be drafted) | the one §1 default that MUST be replaced before any non-demo use | notification, runbook |

---

## 4. Decision record (kickoff walkthrough Q4)

- **FR-X3 new-class matrix rows: not needed for the demo.** Observability inputs are satisfied by
  this industry dataset (`config-default`); business inputs route to the §3 human list; the
  contract and conventions already have structural guards (required CLI flag; FR-H2 routing
  precondition). The matrix remains observability-only (FR-E1) and earns new rows only from
  observed misses, coordinated by the operator.
- This dataset is the first instance of the **industry-profile concept**: a reusable,
  pre-reviewed default set (HITM tier R once validated through a run + approval) keyed by
  industry — `end_user_application` now; other industries later.
