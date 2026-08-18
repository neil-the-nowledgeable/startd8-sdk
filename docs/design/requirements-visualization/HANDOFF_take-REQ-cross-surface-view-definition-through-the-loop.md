# Handoff — Take the cross-surface View Definition through the loop

**For:** the loop operator (a separate implementation session), cold. **Written:** 2026-08-17.
**Goal:** build the **cross-surface View Definition** — lift the node-state taxonomy to a shared owner so
the navig8r AND the cockpit render the same node health, with typed drill/rollup bindings. Self-contained.

---

## 0. What you're building (one paragraph)

The cockpit (kickoff readiness board) and the navig8r (node detail) present the **same** node health in
**different vocabularies** — navig8r `grounded/spec/awaiting/…` (`view_definition.py` REQUIREMENTS_DEFINITION
statuses) vs cockpit `ok/review/blocked/backlog` + `activated` (`portal_spec.py` / `activation.py`) — with
**no shared owner**. This move lifts that to a base `node_state` section in the View Definition (one
canonical state, a **per-surface `presentation`**), projects it **byte-for-byte** to today's navig8r
statuses (empty-default guard), adds a declared cockpit presentation, and declares two typed `surface_links`
bindings: **drill** (cockpit → navig8r node, reusing the `#<key>` full-page route) and **rollup** (navig8r
grounding → cockpit readiness, reusing the `serves`/composition primitive). It is the surface-level twin of
`REQ-feature-capability-composition-rollup.md` and STRATEGY **Move 1** (the hub). Mottainai — a shared
definition + cross-links, **not** a surface merge / cockpit rebuild / new renderer.

- **Spec:** `docs/design/requirements-visualization/REQ-cross-surface-view-definition.md` (7 FRs, BUILD-READY).
- **The analysis it rides on:** `VARIANT_ANALYSIS_ext-cockpit-and-cross-surface.md` (the cockpit placed in
  the SOURCE×TOPOLOGY×PRESENTATION×AUDIENCE map; the drill link today points at the CLI, not navig8r — an open cell).

## 1. Preconditions

```bash
python3 scripts/navigator_spec_delivery_loop.py \
  $(pwd)/docs/design/requirements-visualization/REQ-cross-surface-view-definition.md
# expect: BUILD-READY ✓ (7 FRs)
```

## 2. Build seams (grounded)

- **Shared taxonomy:** navig8r statuses (`view_definition.py` REQUIREMENTS_DEFINITION.vocabulary.statuses)
  ↔ cockpit readiness (`portal_spec.py` `ok/review/blocked/backlog`; `activation.py` `activated`). Add a base
  `node_state` section (canonical state → per-surface `presentation`) to `_SECTIONS` + `BASE_NAVIG8R_DEFINITION`;
  project via `to_render_profile`.
- **Byte-identity:** the shared taxonomy must PROJECT to today's requirements statuses byte-for-byte (empty-
  default guard); guard `tests/unit/wireframe/test_render_profile.py::test_no_profile_is_byte_identical` +
  the view-definition golden-profile tests stay green.
- **Drill:** reuse the `#<key>` route (`wireframe_view/_template.py` `fullview`/`resolveHash`).
- **Rollup:** reuse the `serves` edge (`graph_projection.py:181`) / the composition primitive.

## 3. Relationship to the backlog

The **cross-surface** twin of the graph track: it composes with `REQ-feature-capability-composition-rollup`
(rollup) and STRATEGY Move 1 (drill/hub). Independent of the card-browse track (Move 3/search/Move 2). The
cockpit-side wiring (the drill link, the readiness projection) may need a companion kickoff-side change —
flag it during PREP.

## 4. Git cadence

Hot-main ff discipline: worktree off local `main`, `PYTHONPATH=<wt>/src`, `--ff-only` (rebase onto current
main, re-check tip, ff; if it moved, re-rebase; resolve conflicts by combining). Never force-push `origin`.
Add a `docs(viz): ledger —` entry on delivery.

## 5. Done-when

7/7 FRs verified · shared `node_state` projects to today's navig8r statuses byte-for-byte · the two
`surface_links` (drill/rollup) resolve · app-path byte-identity + view-definition goldens green unedited ·
ruff clean · landed on local `main` via ff + a ledger entry.
