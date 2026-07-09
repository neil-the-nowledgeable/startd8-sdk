# M0 Spike — Findings (Grafana v2 dynamic dashboards)

**Date:** 2026-07-09 · **Verified on:** Grafana **13.1.0** (commit `b309c9bb`), API
`dashboard.grafana.app/v2`, live instance `http://localhost:3000` (service account `sa-1-nemotron-dashboards`).
**Verdict: 🟢 GO** — build M1→M6 per plan v1.1.

M0 is the gate for the whole capability (`DYNAMIC_DASHBOARDS_{REQUIREMENTS,PLAN}.md`). It resolves OQ-1/2/3
against the live upgraded instance and produces the committed artifacts downstream milestones verify against.

## Decision matrix (OQ-1 — provision API) — RESOLVED

Both write paths were tested with a real v2 payload and **round-tripped back as v2 with full fidelity**
(RowsLayout + `Panel` elements + `CustomVariable` all preserved):

| OQ-1 outcome | Observed | Decision |
|---|---|---|
| `POST /api/dashboards/db` accepts v2 | **YES** — returned `status:success`; GET-as-v2 preserved `apiVersion`/`layout.kind`/`elements`/`variables` | **GO (outcome 1)** |
| resource API (`/apis/dashboard.grafana.app/v2/namespaces/<ns>/dashboards`) required | Not required — but it **is** the native path and also creates with fidelity | native path available |
| neither accepts v2 on this build | — | n/a |

**Result: outcome 1 (GO).** The legacy `/api/dashboards/db` accepts v2 (Grafana 13.1 unified storage), so
`grafana_client.upsert_dashboard` extends with minimal change (post `{"dashboard": <v2>, "overwrite": true}`).
**Recommendation:** prefer the **resource API** (k8s-style, native, namespaced) as the v2 provision path and
keep the legacy path as a fallback; record the chosen endpoint in `ProvisioningResult.details["provision_api"]`
(FR-6/R1-F3). Note the resource API requires a real bearer token (anonymous-admin can hit `/api/health` +
legacy `/api/dashboards/db` but **not** `/apis/...` — 401).

## OQ-2 — emit strategy — RESOLVED: Python-side emitter

The v2 payload is **plain JSON** (`apiVersion`/`kind`/`spec{layout,elements,variables}`) — no jsonnet
involved. A Python-side v2 emitter is confirmed viable (NR-5); the classic jsonnet mixin stays classic-only.

## OQ-3 — section variables — RESOLVED: ENABLED and working

`/api/frontend/settings` (authed) shows the required toggles **ON**: `dashboardNewLayouts`,
`dashboardSectionVariables`, `dashboardDefaultLayoutSelector`. A **tab-scoped `variables` array**
(section variable) round-tripped successfully in the composite board.

## Composite board (R2-S6) — all three constructs, one nesting, validated

A single hand-authored board nesting **TabsLayout → TabsLayoutTab** with (a) a **`conditionalRendering`**
`ConditionalRenderingGroup` (`audience == advanced`), (b) a **tab-scoped section variable**, and (c) an
embedded classic **`Panel`** via `GridLayout`→`GridLayoutItem`→`ElementReference` — was **created and
round-tripped intact** by Grafana 13.1.0. This proves the constructs compose and the PanelSpec→element
mapping (R1-S7) works.

## Authoritative construct names (verified, not release-note snapshot)

Captured from the live OpenAPI schema (`/openapi/v3/apis/dashboard.grafana.app/v2`, 125 KB) + a real
dashboard + the composite round-trip. Full map in `v2-construct-names.json`:
- **Layouts:** `GridLayout` · `AutoGridLayout` · `TabsLayout` · `RowsLayout`
- **Containers:** `RowsLayoutRow` · `TabsLayoutTab` · `GridLayoutItem` · `AutoGridLayoutItem` · `ElementReference`
- **Conditional rendering:** `ConditionalRenderingGroup` (spec: `visibility` show/hide, `condition` and/or) with
  `ConditionalRenderingVariable` (operators `equals|notEquals|matches|notMatches`), `ConditionalRenderingData`,
  `ConditionalRenderingTimeRangeSize`
- **Variables:** `CustomVariable` (= the FR-8 `audience` variable shape: `spec{name,query,current,options,...}`),
  plus Constant/Datasource/Adhoc/Query/Interval/Text/GroupBy
- **Element:** `Panel` (`spec{data,description,id,links,title,vizConfig}`)

## Committed artifacts (the M0 deliverables)

| File | Purpose |
|---|---|
| `v2-envelope.golden.json` | the Grafana-normalized composite board — the byte-target the M1 emitter reproduces |
| `v2-envelope-schema.json` | a minimal JSON Schema for the v2 envelope — **CI validates the emitter offline** (no live Grafana); the golden validates against it ✓ |
| `v2-construct-names.json` | verified construct names + `verified_on: 13.1.0` — a 13.1.x rename is a one-line diff (M5 reads this, doesn't hardcode) |

## Carry-forward into M1→M6 (confirmed by the spike)
- **M1:** emitter targets `v2-envelope.golden.json`; the `audience` variable is a `CustomVariable` (matches FR-8).
- **M5:** version probe must read the 13.1 minor / the `dashboardSectionVariables` toggle from
  `/api/frontend/settings` (needs auth) — `check_version()` major-only is insufficient (R1-F1). Provision via the
  resource API (preferred) or legacy; discriminate schema on `apiVersion` presence (R2-S4).
- **M6:** the tab-scoped `conditionalRendering` `audience == 'beginner'` rule is the surface knob; the Era 1
  🛡️ badge rides inside the still-visible `Panel` (coexistence per FR-8).
