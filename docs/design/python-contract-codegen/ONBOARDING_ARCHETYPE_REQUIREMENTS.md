# `onboarding:` Archetype — First-Run Orientation (Requirements)

**Project:** startd8-sdk backend_codegen · **Criticality:** medium
**Version:** 0.1 · **Date:** 2026-08-14
**Format:** det-req/0.1
**Backend:** startd8-python-cascade
**Audience:** cascade app operators + end users of generated FastAPI+HTMX apps
**Pairs with:** `ONBOARDING_ARCHETYPE_PLAN.md`
**Inherits standards:** PC-13 (onboarding is content, not a modal) · EDITORS_ARCHETYPE promotion door ·
det-req-kit `BACKEND_ROUTING` UX rows · attorney-portal ONB shape (**cite only**, not retrofit)

**Status:** IMPLEMENTED (v0.1) on `origin/main` — [PR #463](https://github.com/neil-the-nowledgeable/startd8-sdk/pull/463)
(`1379392`) · FR-1..6 codegen + tests; wireframe harness + household-o11y dogfood
**Pilot:** [`_PILOT_2026-08-14_onboarding-household.md`](./_PILOT_2026-08-14_onboarding-household.md)

---

## 0. Planning Insights

| v0.1 Assumption | Discovery | Impact |
|-----------------|-----------|--------|
| Retrofit attorney portal | Hand-built ONB; bad first dogfood | Pilot = wireframe fixture + household-o11y |
| Absorb Welcome Mat | Chat/download out of scope | NR — tips/welcome only |
| Patch every CRUD empty list | Fights `htmx_generator` | v1: empty-state checklist **on welcome** via live counts |
| Nested `first_run:` map | Extra indirection | Flat `onboarding:` mapping (editors-like strict keys) |

## Overview

Add a `views.yaml` **`onboarding:`** section that generates a first-run **welcome route** with
dismissible **tips-as-content** (no modal/tour library) and an **empty-state checklist** driven by
entity counts. Optional `nav_label` and `redirect_root_if_empty` wire welcome into nav chrome and
root redirect when all checklist entities are empty (FR-2). Inert when absent. Dogfood: SDK wireframe
fixture (harness) + household-o11y (lived).

## Objectives

- O-1: Cascade apps declare first-run orientation in YAML and get `$0` UI.
- O-2: Orientation stays content (PC-13), never a blocking tour.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| quality | Scope creep into Concierge/Welcome Mat | Explicit non-goals | high |
| security | Welcome queries all listed entities | Read-only counts; no write surface | medium |

## Profile

Declared profile: **internal**

## Functional requirements

- **FR-1 — `onboarding:` section.** Top-level `views.yaml` mapping, sibling to `editors:`/`flows:`.
  Absent → zero artifacts. Present → strict parse (unknown keys loud). Touches: views.yaml.
  Verify: `parse_onboarding` returns () when section absent; raises on unknown keys.
- **FR-2 — Grammar.** Required: `route`, `title`. Optional: `lead`, `continue_href` (default `/`),
  `help_href`, `tips` (string list), `empty_states` (entity → copy), `storage_key` (default
  `onboarding_tips_dismissed`), `nav_label` (nav chrome; defaults to `title`),
  `redirect_root_if_empty` (bool; when true and a pages.yaml page owns `/`, GET `/` redirects to
  `route` while every `empty_states` entity still has zero rows). Touches: onboarding_manifest,
  pages_generator.
  Verify: fixture YAML parses to OnboardingSpec with those fields; pages router embeds redirect when flagged.
- **FR-3 — Welcome router + template.** Emit `app/onboarding/welcome.py` +
  `app/templates/onboarding/welcome.html` + aggregator. GET `route` renders title/lead/tips/
  checklist/continue/help. Tips dismiss via `localStorage` + content (not modal). Touches: onboarding_generator.
  Verify: `render_onboarding` emits three paths when declared; tips markup has no modal/dialog role.
- **FR-4 — Empty-state checklist.** For each `empty_states` entity that exists on the schema, welcome
  handler counts rows; count==0 shows the authored copy + link to `/ui/<entitylower>`. Unknown entity
  → loud at render. Touches: onboarding_generator.
  Verify: render fails on unknown entity; generated router references each declared model.
- **FR-5 — Drift + mount.** Register kinds `fastapi-onboarding`, `onboarding-welcome`,
  `onboarding-aggregator` on the views.yaml-derived drift path; unconditional tolerant mount in
  `render_main` (inert when module absent). Touches: drift.py, crud_generator.
  Verify: `generate backend --check` exit 0 on fixture with onboarding; main.py contains
  `onboarding_routers` try/except whether or not section declared.
- **FR-6 — Non-goals enforced.** No tour library, no kickoff Concierge, no attorney retrofit, no
  Welcome Mat chat/download. Touches: this REQ.
  Verify: non-goals section lists them; CRP-lite A/B rejects expansions that reintroduce them.

## Non-goals

- Welcome Mat / Concierge chat or kickoff YAML export.
- Attorney-portal retrofit.
- Multi-step `confirm-walk:` cascade archetype (separate L).
- Replacing household `pages:` `/getting-started` (complementary how-to page).
- Patching every generated CRUD list template in v1.

## Owned fields

App authors own tip strings and empty-state copy in `views.yaml` (and any future prose seam).

## Contract projection

Backend: startd8-python-cascade

| Kind | Name | Notes |
|------|------|-------|
| page | welcome | Generated GET orientation |
| entity | empty_states keys | Must exist on Prisma schema |

## Shipped follow-ups (PR #463)

Post-merge polish landed with the archetype — cite, do not re-spec:

- **Humanized view labels** — `nav_generator.py` titleizes raw view keys (pilot P1-4); see
  [`_PILOT_2026-08-14_onboarding-household.md`](./_PILOT_2026-08-14_onboarding-household.md) §P1-4.
- **Welcome ledger CSS** — `onboarding_generator.py` `render_onboarding_welcome_template` embeds
  clipboard-ledger tokens (FR-FH-11 fallbacks); see
  [`FORM_FIELD_LAYOUT_FR-FH-11.md`](./FORM_FIELD_LAYOUT_FR-FH-11.md).
- **`redirect_root_if_empty`** — `pages_generator.py` redirects GET `/` → `onboarding.route` when
  flagged and every `empty_states` entity is still empty.
- **`nav_label`** — `onboarding_manifest.py` + `nav_generator.py`; nav chrome uses
  `nav_label or title` (wireframe + household declare both).
