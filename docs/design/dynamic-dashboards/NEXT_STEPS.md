# Generate Dynamic Dashboards — Next Steps (session handoff)

**Date:** 2026-07-08 · **Status:** requirements + plan drafted (reflective-requirements through Phase 4.5);
**not yet CRP'd, not yet built.** Blocked on a Grafana upgrade.

This captures where the "generate dynamic dashboards" investigation landed so the next session can pick
it up cleanly.

## What this is

Make **dynamic-dashboard generation a first-class, deterministic (`$0`) capability** in the SDK's
`dashboard_creator` + `startd8-mixin`: emit Grafana 13+ **new-schema (v2)** constructs — **conditional
rendering**, **section-level variables** (per row/tab), and **tabs/rows layout**. First consumer:
**audience/persona personalization** on the Digital Project Workbook (an `audience` runtime variable +
conditional rendering = live in-browser persona switching, no regen, no write). Broader payoff: fleet /
gov-budget / observability-artifact boards.

Docs (this folder):
- `DYNAMIC_DASHBOARDS_REQUIREMENTS.md` (v0.3) — FR-1..11, NR-1..6, OQ-1..7, §Reference-Audit.
- `DYNAMIC_DASHBOARDS_PLAN.md` (v1.0) — M0 (spike, gates all) → M1..M7.

## The one thing to remember (the reframe)

It is **NOT** "add a few panel constructors." Conditional rendering / section vars / tabs are Grafana
**v2-schema** (`apiVersion`/`kind`/`spec`/`elements`/`layout`) constructs, and the whole stack is welded
to **classic `schemaVersion: 39`**:
- `startd8-mixin/lib/dashboards.libsonnet:26` hardcodes `schemaVersion: 39`
- `dashboard_creator/json_validator.py:9` **requires** classic keys → would reject v2
- layout is gridPos (`layout.py`, `apply_layout`), not v2 layout kinds

⇒ This is a **second, additive emit target** (FR-1). Classic stays the default, untouched (NR-1).

## Decisions carried forward

- **Read-only holds.** Audience personalization = a runtime `audience` variable (view toggle), so it
  does **not** violate the Workbook read-only stance (NR-2) and the generated JSON is **identical
  regardless of viewer audience** (strengthens the persona byte-identity guarantee — FR-9).
- **Scope = broad** (user direction, 2026-07-08): the generic v2 capability (FR-1..7), with the Workbook
  audience port (FR-8/9) as the first consumer/proof, then M7 broadens to fleet/gov/o11y.
- **Emit strategy (leaning):** a **Python-side v2 emitter** rather than teaching the classic jsonnet
  mixin the whole v2 schema (NR-5) — confirm in the M0 spike (OQ-2).

## Immediate next steps (in order)

1. **Run CRP** (`/new-cnvrg-rvw-prmpt`, dual-doc) on the requirements + plan → triage → v0.4. *(Was
   offered at session end; not yet run.)* Focus: the v2-schema fork, the provision OQ, external-schema
   dependence, the Workbook one-panel-per-domain snag (OQ-5).
2. **[OPS] Upgrade Grafana to ≥ 13.1** — the hard prerequisite (dynamic dashboards GA in 13; section-level
   variables GA in 13.1, toggle `dashboardSectionVariables`). Due anyway; unblocks everything below.
3. **M0 spike (gates all building)** — on the upgraded instance, resolve the load-bearing unknowns:
   - **OQ-1:** does `POST /api/dashboards/db` accept a v2 payload, or is the resource API
     (`/apis/dashboard.grafana.app/...`) required? Capture the accepted envelope.
   - **OQ-3:** section-variables toggle status; note the same-tab cross-ref limitation (Grafana #122553).
   - **OQ-2:** confirm the Python-side v2 emitter target (the canonical v2 JSON skeleton).
4. **Build M1→M6** per the plan (v2 emit foundation → layout → conditional rendering → section vars →
   validation/provision/version-handling → Workbook audience proof). **M7** (broaden) after.

## Open questions still needing a human/plan decision

- **OQ-4** — Grafana `<13.1` degradation: refuse-with-message vs classic fallback.
- **OQ-5** — Workbook field granularity: coarse "collapse the shielded section for beginner" (recommended
  for v1, small `portal_spec` change) vs per-field panels (fine-grained, bigger change).
- **OQ-6** — disclosure depth: intro-panel-only (v1) vs `explain_input_domain` gains per-tier prose.

## Dependencies / relates-to

- **Audience/persona feature** (owned; cite, don't re-spec): `concierge/audience.py`
  (`KickoffAudience`, `disclosure_tier`, `resolve_audience_preference`), `manifest.py` `AUDIENCE_PROFILES`;
  design in `docs/design/kickoff/PERSONA_EXPERIENCES_{REQUIREMENTS,PLAN}.md`.
- **Digital Project Workbook** (the first consumer): `kickoff_experience/portal_spec.py`,
  `docs/design/kickoff-portal/WORKBOOK_PROJECT_START_REQUIREMENTS.md` (read-only NR-3, live-metrics NR-1).
- **Generator** to extend: `src/startd8/dashboard_creator/` (models/generator/compiler/validation/
  workflow/grafana_client), `startd8-mixin/`.

## Research sources (Grafana 13/13.1 — external, 2026-06 snapshot, re-verify on the live instance)

- Dynamic dashboards (whats-new): https://grafana.com/whats-new/2025-04-10-dynamic-dashboards/
- Section-level variables GA (13.1): https://grafana.com/whats-new/2026-06-11-section-level-variables-for-rows-and-tabs-now-generally-available/
- Grafana 13.1 release blog: https://grafana.com/blog/grafana-13-1-release-all-the-latest-features/
- Conditional rendering (issue #119831): https://github.com/grafana/grafana/issues/119831
- Section-var same-tab limitation (#122553): https://github.com/grafana/grafana/issues/122553
