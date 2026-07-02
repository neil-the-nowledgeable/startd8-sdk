# Kickoff UX / Information Architecture — Implementation Plan

**Version:** 0.1
**Date:** 2026-07-02
**Requirements:** `KICKOFF_UX_REQUIREMENTS.md` (v0.1)
**Branch:** `feat/kickoff-ux-spec` (worktree off `origin/main`).

---

## Planning discoveries (feed the reflection pass)

| What v0.1 assumed | What planning (code read) revealed | Impact |
|-------------------|-----------------------------------|--------|
| The "four things" is a **new mental structure** to design | It maps **1:1 onto the existing 5 `STAGES`** (`data_model`/`manifests`/`value_inputs`/`content`/`run`) — the four things + Build ARE the five stages, just plain-renamed (content de-emphasized). | **FR-UX-1/6 simplify:** the spine is the **existing stages, glossary-renamed** — not a new structure. The redundancy fix = render the renamed spine **once** + attach one next action + completion; move advisories/playbook behind `--verbose`. |
| A glossary may already exist somewhere (OQ-1) | **None exists** — no plain-name/`display_name`/`GLOSSARY` anywhere in `kickoff_experience/`. | **OQ-1 → net-new.** Add a small **presentation module** owning the single-source glossary + the stage→plain-name map + the spine/headline builder. This is the concrete deliverable. |
| `--verbose` toggles depth (OQ-3) | `red-carpet` has only `--json`/`--check`/`--wizard`/`--agent` — **no `--verbose`**. | **OQ-3 → add `--verbose`** (a bool option; Typer convention). Default view = focused; `--verbose` = advisories + playbook. |
| The status "one next action" comes from `ranking.next_action` (OQ-4) | `next_action` (unified via `blocker_cta`) reads "Resolve readiness blocker: **Services**" (jargon); the **advisor playbook rank-1** reads the plain-er **"Author the data-model contract"** (`build_playbook:459`). | **OQ-4 → use `next_steps[0]`** (playbook rank-1), glossary-translated, for the headline action. |
| Two %s both matter (OQ-5) | `completion.overall_pct` (FR-WD-2) is the "how done am I" number; `readiness_score` is a coarse ready-*stage* fraction. | **OQ-5 → headline = `completion.overall_pct`**; readiness drops from the headline (→ `--verbose`, labeled). |
| Greenfield-calm needs advisory data changes (OQ-6) | Derivable at render time: `completion.overall_pct == 0` AND schema absent ⇒ "not started". The alarming "Cascade blocker" lines are already `warn` advisories — they just dominate the default view. | **OQ-6 → presentation-only.** Greenfield headline = calm "begin with Your data"; cascade-blocker advisories move behind `--verbose`. No advisory-data change. |
| The wizard's status wall needs a driver change (FR-UX-9) | The driver (`run_red_carpet_driver`) already renders one step; the **CLI wrapper** `_run_red_carpet_wizard` passes `render_state=_render_red_carpet_state` (the full wall) as the per-iteration render. | **FR-UX-9 → swap the render callback** to a compact spine+step renderer. No driver change. |

**Net:** the spec is almost entirely **presentation** over unchanged mechanisms — one new small module +
a `--verbose` flag + render swaps. The biggest "aha" is that the four-things model already exists as the
5 stages; we rename, don't restructure.

---

## Approach & step map

### Step 1 — The presentation module (FR-UX-1/2/3/6) — the single source
- New `src/startd8/kickoff_experience/presentation.py` (surface-neutral, `$0`):
  - `GLOSSARY` — the one plain-name map: `{"data_model":"Your data", "manifests":"Your screens",
    "value_inputs":"Your settings", "content":"Placeholder content", "run":"Build"}` + a `WHAT_IS`
    one-liner per thing. **Single source** all surfaces cite (FR-UX-2).
  - `build_spine(state) -> list[SpineNode]` — the four-things + Build spine from `state.stages` /
    `next_stage` / `completion`: each node = `{key, plain_name, status(done|next|todo|later), detail?}`,
    `content` flagged `later` (de-emphasized, FR-UX-3).
  - `headline(state) -> {pct, plain, you_are_here, next_action}` — the one completion % (FR-UX-7), the
    plain "you are here", and the single next action from `next_steps[0]` glossary-translated (FR-UX-4/OQ-4),
    with the **calm greenfield** variant when `overall_pct==0` + schema absent (FR-UX-8/OQ-6).

### Step 2 — Rewrite the status view (FR-UX-4/5/6/7/8)
- `cli_kickoff._render_red_carpet_state(state, *, verbose=False)`: default = the spine (rendered once) +
  headline (one %, you-are-here) + the single next action + a "N more → `--verbose`" pointer. **Remove**
  the parallel Insights + Next-steps dumps from the default path (UX-P3). Under `verbose=True`, append the
  advisories + ranked playbook (the current detail), plain-labeled.
- Add `verbose: bool = typer.Option(False, "--verbose")` to `red_carpet_cmd`; thread it into the render.
  `--json` unchanged (NR-3).

### Step 3 — Compact wizard render (FR-UX-9/10)
- New `presentation.render_wizard_step(action, spine) -> str/lines` — a compact one-step view (spine
  "Step N of M · plain name" + found/needed/action in glossary language). In `_run_red_carpet_wizard`,
  pass this as `render_state` **instead of** `_render_red_carpet_state`, and drop the opening full wall —
  one framing line, then step-by-step (FR-UX-9). Translate the wizard's found/needed via the glossary.

### Step 4 — Help text / mode roles (FR-UX-11)
- Reword `red-carpet` help so each mode's role is one line: default = *glance*, `--wizard` = *do*,
  `--agent` = *talk*, `--json`/`--verbose` = *detail*.

### Step 5 — Cross-surface note (FR-UX-12)
- The web rail (`web.py`) is out of scope to rebuild here (NR-4), but the glossary + `build_spine` are
  importable by it; add a short docstring/pointer so the later web wizard consumes the same module. No web
  code change this increment.

### Step 6 — Tests + snapshots
- `presentation.py`: glossary covers all 5 stages; `build_spine` marks the right node `next`/`later`;
  `headline` picks `completion.overall_pct` + the greenfield-calm variant; next action = `next_steps[0]`
  translated (no jargon).
- CLI render: default output contains **no** "Cascade blocker" / raw `value_path` jargon and shows exactly
  one next action; `--verbose` restores the advisory/playbook detail; `--json` byte-unchanged (regression).
- Wizard render: the compact step view contains the spine + one step and **not** the full stage/insights
  wall (a snapshot asserts the wall is absent).
- No-jargon guard: the default status + wizard output contain none of `{cascade, manifest, value_path,
  front bookend, buckets}` (a lint-style test over the rendered strings).

---

## §7 Validation Strategy
- **Focus proof:** default `red-carpet` output ≤ ~12 lines and contains exactly one "do next" action.
- **No-jargon proof:** default + wizard rendered strings contain none of the internal-vocabulary terms
  (glossary is the only naming path).
- **Say-once proof:** a given gap string appears at most once in the default view.
- **Backward compat:** `--json` unchanged; `--verbose` reproduces today's detail; all kickoff suites green.
- **Calm greenfield:** a blank project's headline is informational (not error-colored) and says "begin
  with Your data".

## Risks
- **R1 — Hiding real problems behind `--verbose`.** Mitigation: the *one* next action always surfaces the
  top gap; `--verbose` is additive detail, and `--check` (error advisories) is unchanged for CI.
- **R2 — Glossary drift** if surfaces re-name locally. Mitigation: single-source `GLOSSARY` (FR-UX-2) + the
  no-jargon test; no surface hardcodes a plain name.
- **R3 — Snapshot brittleness.** Mitigation: assert on presence/absence of key tokens, not exact layout.
