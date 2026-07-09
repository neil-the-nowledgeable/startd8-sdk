# Generate Dynamic Dashboards — Plan

**Version:** 1.0 (tracks requirements v0.3)
**Date:** 2026-07-08
**Requirements:** `DYNAMIC_DASHBOARDS_REQUIREMENTS.md`

The work is a **second (v2) emit target** alongside the untouched classic path, proven end-to-end on the
Workbook. Two strategy forks are resolved by an up-front spike (M0) before building.

---

## M0 — Spike on the upgraded Grafana (resolves OQ-1, OQ-3) — **do first, gates everything**
- Once Grafana ≥13.1 is up: hand-author one v2 dashboard (`apiVersion`/`kind`/`spec` with a tab, a row, a
  section variable, and a conditional-rendering rule) and confirm it renders + a `dashboardSectionVariables`
  status.
- **Verify the provision API (OQ-1):** does `POST /api/dashboards/db` accept v2, or is the resource API
  (`/apis/dashboard.grafana.app/...`) required? Capture the exact accepted payload envelope.
- **Decide OQ-2 (emit strategy):** confirm a **Python-side v2 emitter** is viable (lean recommendation —
  the mixin is deeply classic; teaching it the whole v2 schema is NR-5). Record the v2 JSON skeleton.
- **Output:** a de-risking note + the canonical v2 JSON envelope the emitter targets. No SDK code yet.

## M1 — v2 emit foundation (FR-1, FR-5, FR-10)
- New `dashboard_creator/v2/` (emitter + models) OR a `schema="v2"` branch in the workflow. Additive:
  extend `DashboardSpec`/`PanelSpec` with optional `layout`, per-element `conditional`, section `variables`
  (FR-10) — classic path and existing consumers untouched.
- Reuse the existing PanelSpec→panel mapping for the leaf panels; wrap them in v2 `elements` + `layout`.
- Deterministic: `json.dumps(sort_keys=True)`; a golden pins byte-stability.
- **Verify:** a minimal v2 spec compiles to the M0 envelope; classic specs are byte-identical to today.

## M2 — Tabs/rows layout (FR-4)
- A `layout` descriptor (tabs → rows → panels, nesting) → v2 layout kinds (`TabsLayout`/`RowsLayout`/
  `AutoGridLayout`/`GridLayout`); auto-grid vs custom selectable.
- **Verify:** a 2-tab / 2-row spec renders the sections; content outline populated.

## M3 — Conditional rendering (FR-2)
- Per-element `conditional`: condition types variable-value (`equals|notEquals|matches|notMatches`),
  data-presence, time-range-size; AND/OR groups → the conditional-rendering group construct.
- **Verify:** a panel shown only when `var == 'x'`; hidden otherwise; AND/OR compose.

## M4 — Section-level variables (FR-3)
- Per-row/tab `variables`; section-first resolution. Note the same-tab cross-reference limitation
  (issue #122553) — validate against it.
- **Verify:** two sections filter independently under one time range.

## M5 — Validation + provisioning + version handling (FR-7, FR-6, FR-11)
- Make `json_validator` schema-aware (classic keys OR v2 `apiVersion`/`kind`/`spec`); validate v2
  well-formedness.
- Provision path per M0/OQ-1 (`/api/dashboards/db` or resource API); preserve UID/idempotent upsert +
  the FR-5 collision guard already in `portal_build`.
- **Version detect (FR-11/OQ-4):** query Grafana version/capabilities; `<13.1` → refuse-with-message (or
  classic fallback, per the OQ-4 decision) — never a silently-broken board.
- **Verify:** v2 board upserts idempotently; a `<13.1` target is refused with an actionable message.

## M6 — Workbook audience consumer (FR-8, FR-9) — the proof
- Add an `audience` custom variable (beginner/intermediate/advanced), **default from
  `resolve_audience_preference(project_root)`**; wire in `portal_spec.py` via the audience feature's
  public API (cite, don't re-implement).
- **Disclosure:** intro/prose panels per tier with `audience == …` show-rules (OQ-6: intro-first for v1).
- **Surface (OQ-5 decision needed):** either render the `AUDIENCE_PROFILES`-shielded fields as a separate
  **collapsible row** hidden for beginner (coarse, cheap), or split fields into per-field panels (fine,
  bigger `portal_spec` change). Recommend coarse for v1.
- One deterministic JSON per project; switching `audience` re-renders in-browser, no write (FR-9, NR-2).
- **Verify:** the board defaults to the project audience; flipping the variable changes prose density +
  shielded-field visibility with zero regeneration and zero writes to `inputs/`/`confirmed.yaml`.

## M7 — Broaden (optional, OQ-7)
- Fleet (per-service section filters), gov-budget (per-department sections/tabs), o11y-artifact boards opt
  into the v2 constructs. Sequence after the Workbook proof.

---

## Design notes / risks
- **Emit strategy (OQ-2).** Lean **Python-side v2 emitter** — the classic jsonnet mixin stays for classic;
  v2 is a separate, simpler JSON builder. Avoids a parallel v2 jsonnet library (NR-5).
- **Classic path is sacrosanct (NR-1).** M1's golden pins classic byte-equivalence; no existing consumer
  changes until it opts in (FR-10).
- **Provision uncertainty (OQ-1) is the top risk** — M0 resolves it before any build; if the resource API
  is required, `grafana_client` gains a v2 method.
- **Workbook structural change (OQ-5)** — the one-markdown-panel-per-domain layout limits field-level
  conditional rendering; take the coarse (row-collapse) path for v1 to keep `portal_spec` change small.
- **External-schema drift** — the Grafana v2 construct names are a 2026-06 snapshot; M0 pins them against
  the live instance before the emitter hardcodes anything.

## Traceability
| FR | Milestone |
|---|---|
| FR-1, FR-5, FR-10 | M1 |
| FR-4 | M2 |
| FR-2 | M3 |
| FR-3 | M4 |
| FR-6, FR-7, FR-11 | M5 |
| FR-8, FR-9 | M6 |
| (broaden) | M7 |
| (verify OQ-1/2/3) | **M0 (gates all)** |
