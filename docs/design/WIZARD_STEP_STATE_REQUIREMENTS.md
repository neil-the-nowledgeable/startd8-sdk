# Wizard step-state primitive (P0-1, shared-floor) — Requirements

**Version:** 0.2 (post-investigation)
**Date:** 2026-06-10
**Status:** IMPLEMENTED 2026-06-10 — FR-WZ-1..5 in `backend_codegen` (`flows_manifest` + `flow_generator`:
flow router start/resume/advance/back over a draft step pointer, tolerant per-step content seam,
tolerant `on_finish` hook, aggregator mount). Runtime-proven (TestClient: start→advance→back→finish→
resume persist). 355 passed.
**Scope:** The shared-floor **step-state machine primitive** the StartDate shared-floor answer asked
for — *not* a monolithic `kind: wizard`. A multi-step flow over a **draft entity**: persist the current
step, advance, go back, resume. Serves both StartDate (résumé wizard) and navig8 (decision-tree
traversal — "persist step state, advance, go back, resume"). The **step content** (pickers, forms) stays
**app-owned glue**; the SDK owns the navigation/state plumbing. **$0, deterministic, 0 LLM.**
**Component:** `backend_codegen` — new `flows_manifest.py` + flow-router/shell generation, main.py mount.

## 0. Planning insights (from a code-investigation pass)

| Assumption | Discovery | Impact |
|------------|-----------|--------|
| It's a `view_codegen` `kind: wizard` | view_codegen is read-only composite views (closed kind vocab); the shared-floor answer explicitly says **primitive, not a view kind** | Build in **backend_codegen** (it mutates a draft entity + generates routes), via a `flows:` section in views.yaml (already threaded as `views_text`). |
| The SDK injects a step column | The contract is the source of truth; magic columns break that | The flow declares a `step_field` that **must be an existing column** on the draft entity (loud-fail otherwise). |
| Step content is generated | navig8 vs résumé step bodies differ entirely; the team owns them (the de-risker they offered) | The SDK generates the **shell + navigation**; step bodies come through a **tolerant `{% include … ignore missing %}` seam** (the AI-trigger pattern). |
| `on_finish` is bespoke per flow | `view_codegen` already has the `_COMPUTE_RENDERERS` registry precedent for binding generated→owned fns | `on_finish` is a **tolerant registry hook** (owned fn looked up by name; no-op if absent) — résumé serialization stays app-owned. |

## 1. Functional Requirements

- **FR-WZ-1 — `flows:` manifest.** views.yaml may carry a `flows:` section: each flow has `name`,
  `draft_entity`, `step_field` (a column on that entity holding the current step key), an ordered
  `steps` list, and optional `on_finish` (a registered owned-fn name). Strict-parsed; unknown entity /
  unknown `step_field` column / empty `steps` fail loud against the contract. Verify: a valid flow
  parses; a bad entity/field/empty-steps raises.

- **FR-WZ-2 — Generated flow router (start / resume / advance / back).** Emit `app/flows/<name>.py`
  with a `flow_<name>_router`:
  - `POST /flow/<name>/start` → create a `draft_entity` row with `step_field = steps[0]`, redirect to it.
  - `GET /flow/<name>/{id}` → load the draft; render the shell at its current step (resume = this).
  - `POST /flow/<name>/{id}/advance` → if at the last step, run `on_finish` (if set) then redirect;
    else set `step_field` to the next step, persist, redirect.
  - `POST /flow/<name>/{id}/back` → set `step_field` to the previous step (clamped at first), persist.
  Verify: start creates a draft at step[0]; advance/back move the pointer and persist; advancing past
  the last step invokes the finish path; back at step[0] stays.

- **FR-WZ-3 — Per-step content via a tolerant seam.** The shell renders the current step with
  `{% include "flows/<name>/_step_" ~ item.<step_field> ~ ".html" ignore missing %}` + Back/Next
  controls. The SDK emits a placeholder shell template; **per-step bodies are app-owned** (the include
  is inert when a body is absent). Verify: the shell carries the dynamic tolerant include + the nav
  controls bound to the advance/back routes.

- **FR-WZ-4 — `on_finish` tolerant registry hook.** When `on_finish: <fn>` is set, the finish path
  calls a registered owned function looked up by name from a tolerant registry (absent ⇒ no-op + a
  logged note), mirroring `view_codegen._COMPUTE_RENDERERS`. Verify: a flow with `on_finish` generates
  the registry lookup + tolerant call; without it, the finish path just redirects.

- **FR-WZ-5 — Tolerant mount + inert when absent.** `app/main.py` mounts each `flow_<name>_router`
  via the optional-import pattern (like `ai_ui_router`); a contract/manifest with no `flows:` emits no
  flow modules and an unchanged main.py mount set. Verify: main.py carries the tolerant flow mount; a
  no-flow project emits no `app/flows/`.

## 2. Non-Requirements

- **No generated step *content*** — pickers (P1-1), nested forms (P1-2), validation are app-owned glue
  (shared-floor answer: StartDate-only until a 2nd consumer appears).
- **No branching engine (v1).** Linear `steps` (next/prev). Non-linear traversal (a decision tree
  picking the next step from an answer) is a v2 — the MVP delivers the forward/back/resume spine both
  apps share; a branching `advance?to=<step>` is a follow-on.
- **No LLM / no client JS.** Plain PRG routes.

## 3. Open Questions

- **OQ-WZ-1 — branching.** v1 is linear; navig8's tree may want `advance?to=<step>` (validated against
  `steps`). Defer until navig8 actually needs it (lean: add `to=` as an optional override later).
- **OQ-WZ-2 — finish destination.** Where does the finish path redirect — the draft's detail page, a
  configurable route, or `on_finish`'s return? v1: the draft detail page (`/ui/<entity>/{id}`).

## 4. Acceptance

1. `flows:` parses strict; bad entity/field/empty-steps → loud.
2. start → draft at `steps[0]`; advance/back move + persist the pointer; past-last runs the finish
   path; back at first is a no-op. (Runtime-proven via TestClient.)
3. The shell includes the dynamic per-step seam + nav controls; per-step bodies are app-owned/inert.
4. No-flow projects are unchanged (no `app/flows/`, main.py mount set identical).
