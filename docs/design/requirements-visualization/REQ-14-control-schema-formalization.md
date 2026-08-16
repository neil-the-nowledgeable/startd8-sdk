# Control-Schema Formalization — Requirements

**Project:** startd8-sdk   **Criticality:** medium
**Version:** 0.2 (post-planning — self-reflective update)   **Date:** 2026-08-15
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** *(plan deferred — spec-only; delivered via the Spec Delivery Loop)* · architecture `ARCHITECTURE_navig8r-presentation-definition-inheritance.md` (§7 step 4 — control-layer schema)
**Inherits standards:** det-req-kit · NODE-SCHEMA v0.3.9 · NAMING_CONVENTION · REQ-10-view-definition-cascade (parent keystone) · REQ-11/REQ-12/REQ-13 (siblings) · SOTTO_DESIGN_PRINCIPLE
**Audience:** operator / SDK contributors / cross-repo adopters (legal · benchmark · dev-os)
**Trust boundary:** local filesystem + authored definitions; no LLM; no network
**Data classification:** internal

> **Readable handle:** `feature/sdk-navigator-formalizes-the-control-panel-cc54b3a8`
> **Semantic name:** *SDK navigator formalizes the control-panel structure as a data schema in the View Definition control section by reconciling the base to carry the panel position and group labels and hints and projecting it so control is inspectable, overridable, and validated at the definition layer while the renderer stays byte-identical and renderer consumption is deferred to a later step.*
> **Canonical ref:** `cc:intent:requirements-visualization:feature:req-14`

## 0. Why this exists — formalize control as data, before (not with) renderer consumption

Architecture §7 step 4 asks to "formalize the consolidated top-right options as the definition's
`control` section." The base already carries a stub — `control={"panel": "top-right", "groups":
["view","overlays","template-anatomy"]}` — but it holds only group **keys**, not the labels/hints the
panel actually shows, and nothing validates or cascades it as a real schema. This REQ turns `control`
into a **first-class, cascade-able, validated, inspectable data schema** (the group set with labels +
hints + order, plus the panel position), reconciled to the renderer's actual values. It **does not** wire
the renderer to consume it — that is deliberately deferred (see §0 insight) — so the change is
**byte-identical everywhere**.

## 0. Planning Insights (self-reflective update)

> Planning against the real `_template.py` control panel revealed why the naive "data-drive the panel"
> reading of step 4 is a trap — and scoped this REQ to the safe half:

| v0.1 assumption | Planning discovery | Impact |
|-----------------|--------------------|--------|
| Step 4 = make the definition's `control` drive the rendered panel | The `#debug` panel is **JS-generated in a template literal** (`_template.py:774-789`); the 3 group headers are hardcoded strings and each toggle (`structOnly`/`combined`/`hideScaffold`/`scaffold`/`scaffoldOnly`) has a **bespoke JS handler + body-class CSS**. Data-driving it is deep, risky template surgery for a **developer debug tool** | **NR-1**: this REQ formalizes `control` as DATA only; renderer consumption is a separate later step — mirroring how REQ-10 formalized `theme` as data before REQ-11 activated it |
| `control.groups` can stay a positional list | Overriding one group must be atomic — a positional list can't (REQ-10's keyed-collection rule) | **FR-1**: `groups` becomes a **keyed map** (`{view: {...}, overlays: {...}}`), merged by id |
| The labels can be invented | Byte-identity for the (future) consumer requires the base to carry the renderer's **exact** headers | **FR-1**: reconcile to the real `_template.py` strings (`View` / `· pick one (Full is default)`, etc.) — the Genchi Genbutsu anchor, exactly like REQ-11's theme reconciliation |

**Resolved open questions:** OQ-1 (drive the renderer now?) → no, defer (NR-1). OQ-2 (list or keyed?) →
keyed map merged by group id (FR-1). OQ-3 (scope of a group?) → panel position + group key/label/hint/
order; NOT the toggles' behaviors (NR-2).

## Overview

Reconcile `BASE_NAVIG8R_DEFINITION.control` to a richer schema — `{panel, groups}` where `groups` is a
**keyed map** of `{label, hint, order}` carrying the panel's real headers. Let `control` ride the per-leaf
cascade (a domain overrides/adds/reorders a group by key) and be inspectable via `navigator
view-definition --dump`/`--diff`. Extend `validate_definitions` to govern `control` (each group has a
label; the panel position is known). The renderer and `RenderProfile` are **untouched** — control is not
consumed in output this step (NR-1), so every render is byte-identical.

## Objectives

- **O-1:** `control` is a first-class data schema — target: the base carries the panel position + a keyed group map (label/hint/order) matching the renderer's real headers; a domain can override/add/reorder a group.
- **O-2:** It's governed + inspectable — target: `validate_definitions` checks `control`; `view-definition --dump`/`--diff` surfaces it; it rides the cascade.
- **O-3:** Byte-identical — target: no renderer/`RenderProfile`/template change; `test_no_profile_is_byte_identical` + the debug-panel test pass unedited; all domain renders unchanged.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| complexity/quality | Data-driving the JS panel = deep, risky template surgery for a dev tool | NR-1: formalize control as DATA only; defer renderer consumption to a later step | high |
| quality | Positional group list makes an override non-atomic | FR-1: `groups` is a keyed map merged by id | medium |
| quality | Invented labels would break the future consumer's byte-identity | FR-1: reconcile to the renderer's exact header strings | medium |
| scope | Formalizing toggle behaviors/CSS as data | NR-2: panel position + group key/label/hint/order only; toggles stay renderer-internal | medium |

## Functional requirements

- **FR-1 — Reconcile base.control to a keyed group schema.** `BASE_NAVIG8R_DEFINITION.control` becomes `{panel: "top-right", groups: {<key>: {label, hint, order}}}` — a keyed map carrying the renderer's actual headers (`view` → `{label: "View", hint: "· pick one (Full is default)", order: 0}`, `overlays` → `{label: "Overlays", hint: "· additive", order: 1}`, `template-anatomy` → `{label: "Template anatomy", hint: "· debug", order: 2}`), replacing the positional key list. Name: Navigator reconciles the base control section to a keyed group schema carrying the panel's real labels hints and order. Touches: `src/startd8/navigator/view_definition.py`, `tests/unit/navigator/test_view_definition.py`. Lives: code src/startd8/navigator/view_definition.py. Approve?: does base.control carry the real panel labels/hints as a keyed group map?. Verify: `BASE_NAVIG8R_DEFINITION.control["groups"]["view"] == {"label": "View", "hint": "· pick one (Full is default)", "order": 0}` and `["panel"] == "top-right"`; `groups` is a dict, not a list. Serves: O-1
- **FR-2 — Control rides the per-leaf cascade (keyed by group).** Resolving a domain that overrides `control.panel` or one group's `label` keeps the base's other control values and other groups (keyed merge by group id — atomic override, base propagation). Name: A domain overrides one control group or the panel position while inheriting the rest of the base control. Touches: `src/startd8/navigator/view_definition.py`, `tests/unit/navigator/test_view_definition.py`. Lives: code src/startd8/navigator/view_definition.py. Approve?: does control cascade per-leaf with keyed group merge?. Verify: a synthetic domain overriding `control.groups.view.label` keeps the base `overlays`/`template-anatomy` groups and the base `panel`; a base `control.panel` change reaches a non-overriding domain. Serves: O-1
- **FR-3 — Control is inspectable via the CLI.** `navigator view-definition --dump`/`--diff` surfaces the resolved `control` schema (it is part of the resolved definition JSON), so an author sees the panel structure without reading Python. Name: The view-definition CLI surfaces the resolved control schema in its dump and diff. Touches: `tests/unit/navigator/test_sources_and_cli.py`. Lives: test tests/unit/navigator/test_sources_and_cli.py. Approve?: does the CLI dump include the control schema?. Verify: `view-definition --name requirements` JSON includes `control.groups.view.label == "View"` (inherited from base); `--name <domain> --diff` shows a domain's control override if any. Serves: O-2
- **FR-4 — validate_definitions governs control.** `validate_definitions` (EC-6) is extended to check `control`: every group has a non-empty `label`, and `panel` is one of the known positions (e.g. `top-right`); a malformed control is reported as an issue. Name: Definition governance validates that every control group has a label and the panel position is known. Touches: `src/startd8/navigator/view_definition.py`, `tests/unit/navigator/test_view_definition.py`. Lives: code src/startd8/navigator/view_definition.py. Approve?: does validate_definitions flag a malformed control schema?. Verify: the shipped registry still validates clean; a synthetic definition whose `control.groups.x` lacks a `label` (or whose `panel` is unknown) is reported by `validate_definitions`. Serves: O-2
- **FR-5 — Byte-identical (renderer + profile untouched).** No renderer, template, or `RenderProfile` change — `control` is not projected to the profile or consumed in output this step (renderer consumption deferred, NR-1). The app path and every domain render are byte-identical. Name: Formalizing control as data leaves the renderer RenderProfile and every rendered output byte-identical. Touches: `tests/unit/wireframe/test_render_profile.py`, `tests/unit/navigator/test_view_definition.py`. Lives: test tests/unit/wireframe/test_render_profile.py. Approve?: is every rendered output unchanged?. Verify: `test_no_profile_is_byte_identical` passes unedited; the debug-panel test (`test_debug_view_mode_panel_is_profiled_and_byte_safe`) passes unedited; `to_render_profile` gains no `control` field. Serves: O-3

## Non-requirements

- **NR-1:** Renderer consumption is DEFERRED. The `#debug` panel still emits its hardcoded group headers + toggles; data-driving the panel from `control` (the risky JS/template edit) is a SEPARATE later step. This REQ formalizes `control` as DATA only — mirroring REQ-10 formalizing `theme` as data before REQ-11 activated it.
- **NR-2:** Panel position + group `key`/`label`/`hint`/`order` only. The individual toggles' behaviors, IDs, and body-class CSS (`structOnly`/`combined`/`hideScaffold`/`scaffold`/`scaffoldOnly`) stay renderer-internal — NOT formalized as data this step.
- **NR-3:** No new control widgets/types/positions — the schema mirrors today's three groups and the current `top-right` panel; it does not invent controls the renderer doesn't have.
- **NR-4:** No `RenderProfile` change — `control` is not projected to the profile (no consumer needs it until renderer consumption lands); it lives in the `ViewDefinition`/`ResolvedDefinition` and is reached via `resolve` + the CLI dump.

## Appendix A — Accepted (with where merged)
*(none yet — CRP incoming)*

## Appendix B — Rejected (with rationale)
*(none yet — CRP incoming)*

## Appendix C — Incoming review rounds
*(none yet)*

*v0.2 — Post-planning self-reflective update. Scoped to data-formalization (renderer consumption deferred, NR-1); groups keyed not positional; base reconciled to the renderer's real headers; 3 open questions resolved.*
