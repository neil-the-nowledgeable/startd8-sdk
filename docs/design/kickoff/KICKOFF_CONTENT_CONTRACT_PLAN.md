# Kickoff Content Contract — Implementation Plan

**Version:** 1.1 (tracks Requirements v0.3; lessons-hardened)
**Date:** 2026-07-06
**Status:** Draft — ready for CRP
**Companion:** `KICKOFF_CONTENT_CONTRACT_REQUIREMENTS.md`

---

## Approach

Make the kickoff experience honor the content contract it prescribes for projects. The instructional
content is *already authored* in `concierge_templates/*.md`; the work is (1) authoring one new
generic experience-level intro, (2) surfacing the existing content at runtime via the proven
`render_template_content` loader, and (3) plumbing intro/posture through the guided view-model so
parity/byte-identity tests stay green. No new engine, no LLM, no writes on the read path.

## Discoveries carried from planning (see Requirements §0)

- Templates are per-project scoped (placeholders + banner) → the generic intro must be new content.
- Bare `kickoff` exits 2 today → a `invoke_without_command=True` callback flips it to 0.
- `render_template_content`/`get_template_entry` (`writes.py:255-267`) already render bytes at runtime (used by `web.py`) → reuse, don't reinvent.
- Guided CLI is a pure function of `build_guided_view` → intro/posture must be view-model keys.
- Posture is never persisted → guided can only *inform*, not record.

## Steps

### Step 1 — Author the generic intro doc + render-only loader (FR-1, FR-6)
- **New file** `src/startd8/concierge_templates/KICKOFF_EXPERIENCE_INTRO.md` — generic, no `<Project>`
  placeholders, no TEMPLATE banner. Content: what kickoff is (machines-draft/humans-decide),
  the recommended order (survey → assess → instantiate → cascade), the two postures in one line each,
  and pointers to `kickoff explain` / the per-project `KICKOFF_INTRO.md`.
- **Render-only loader (lessons-hardening fix).** Do NOT register it in the manifest or `_KICKOFF_FILES`
  — the manifest is derived *solely* from the instantiate write inventory by deliberate anti-drift
  design (`writes.py:186-195`), and there is no render-only tier. Instead add a small public
  `load_experience_doc(rel: str) -> str` in `writes.py`, backed by the existing `_load_template`
  `importlib.resources` read (`writes.py:113-116`), that returns packaged bytes WITHOUT joining the
  write/download set. This keeps FR-6 single-source without writing a generic doc into every project.
- **Compact form:** a `## TL;DR` section (or a leading fenced block) the runtime slices for the
  one-screen intro (FR-2/FR-3 show compact; `kickoff explain --intro` shows full).

### Step 2 — Bare-group orientation callback (FR-2, FR-7)
- Add `@kickoff_kernel_app.callback(invoke_without_command=True)` in `cli_concierge.py` (near line 40).
- Body: `if ctx.invoked_subcommand is None:` print compact intro (Step 1) to **stdout** (this is the
  primary content of the bare command, not a courtesy) then `typer.echo(ctx.get_help())`; else return.
- Exit 0. Document the 2→0 compat change (risk R1).
- Keep the deprecated `concierge_app` alias callback unchanged.

### Step 3 — `kickoff explain` verb (FR-5, FR-8)
- New subcommand `kickoff explain [domain]` in `cli_concierge.py`, registered like the others
  (`cli_concierge.py:517-525`).
- No arg / `--intro`: render `KICKOFF_EXPERIENCE_INTRO.md`. `--inputs` or a domain slug: render
  `KICKOFF_INPUTS_EXPLAINED` (whole, or note the domain section). All via `render_template_content`.
- `--json` returns `{schema, action:"explain", doc, content}`; human path prints markdown.
- This is the reachable home for clauses E, G, H (FR-8: the boundary + pre-demo warning already live
  in `KICKOFF_INPUTS_EXPLAINED_TEMPLATE.md` §5 / INTRO §4).

### Step 4 — Guided intro + posture through the view-model (FR-3, FR-4, FR-9, FR-10)
- In `kickoff_experience/concierge_view.py::build_guided_view` (`:624-662`) add sibling keys:
  - `intro`: `{show: bool, mode: "full"|"brief", text_key: "kickoff-experience-intro"}` — `show`/`mode`
    computed read-only from `docs/kickoff/inputs/` presence + the `--brief/--no-intro` flag (FR-10).
  - `posture`: `{default_mode, prototype_line, production_line, actionable_hint:
    "startd8 kickoff instantiate --posture <prototype|production>"}` — information only (FR-4). Reuse
    the `POSTURE_BANNER` pattern (`concierge_view.py:294-298`).
- Add matching entries to `guided_parity_digest` (`:665-686`) and `render_guided_lines` (`:720-751`)
  so TUI/served parity holds.
- In `cli_concierge.py::kickoff_guided` (`:468-489`) render the new `view["intro"]`/`view["posture"]`
  blocks *before* Orient, drawing purely from the view-model (no ad-hoc content). Thread a
  `--brief/--no-intro` typer option.

### Step 5 — Tests
- Extend `test_guided_experience_m4.py`: assert new `intro`/`posture` keys appear in
  `build_guided_view` and that CLI `--json == build_guided_view`, digest parity holds.
- Extend `test_guided_experience_m1.py`: the source-inspection no-writer guard still passes (the new
  code calls no `apply_write_plan(`/`open(`); intro decision is read-only via a stat helper).
- New `test_kickoff_intro.py`: bare `kickoff` exits 0 and prints intro+help; `kickoff explain`
  renders template bytes == `render_template_content(...)`; `--json` clean; FR-10 heuristic
  (inputs-present ⇒ brief) and `--brief` flag.
- Byte-identity: confirm `assess --json`/stdout unchanged (Step 2/4 touch only `kickoff`/`guided`,
  not `assess`), keeping `test_guided_offer_cli.py` green.

### Step 6 — Docs/capability
- Note the new `kickoff explain` verb + bare-group intro in the kickoff docset; capability-index
  touch if the command surface is indexed.

## Risks

- **R1 (compat):** bare `kickoff` exit 2 → 0. Low blast radius (bare group is rarely scripted);
  documented; the friendlier behavior is the intent. Mitigate: keep `--help` behavior identical.
- **R2 (parity break):** forgetting to update `guided_parity_digest`/`render_guided_lines` fails
  `test_guided_experience_m4.py` loudly — caught, not silent.
- **R3 (render-only doc leaking into instantiate/download inventory):** the manifest is derived
  *only* from `_KICKOFF_FILES + _AUTHORING_FILES` (`writes.py:191-195`), so there is no way to add a
  manifest entry that isn't also a written/downloadable file. Mitigate (per §0.1): use the separate
  `load_experience_doc` loader — never touch `_KICKOFF_FILES` or `_TEMPLATE_GROUPS`. Test: assert
  `kickoff_template_manifest()` and `build_instantiate_plan` output are byte-unchanged by this feature.
- **R4 (drift, FR-6):** any temptation to hand-copy intro text into a Python string reintroduces
  drift. Mitigate: single loader path, test asserts equality to `render_template_content`.

## Requirement → step trace

| FR | Step(s) |
|----|---------|
| FR-1 | 1 |
| FR-2 | 2 |
| FR-3 | 1, 4 |
| FR-4 | 4 |
| FR-5 | 3 |
| FR-6 | 1, 3, 5 (equality test) |
| FR-7 | 2, 3, 4 |
| FR-8 | 3 |
| FR-9 | 4, 5 |
| FR-10 | 4, 5 |

## Implementation status (2026-07-06)

**IMPLEMENTED** on branch `feat/kickoff-content-contract`. All 6 steps landed; 9 new tests +
618 existing kickoff/concierge tests green.
- Step 1 — `KICKOFF_EXPERIENCE_INTRO.md` (packaged + canonical mirror) + `load_experience_doc`
  render-only loader (`writes.py`).
- Step 2 — `@kickoff_kernel_app.callback(invoke_without_command=True)` (bare `kickoff` exit 2 → 0).
- Step 3 — `kickoff explain [--intro] [--json]` verb.
- Step 4 — `intro`/`posture` keys in `build_guided_view` + digest + `render_guided_lines` + CLI
  render + `--brief/--no-intro`.
- Step 5 — `tests/unit/kickoff_experience/test_kickoff_intro.py`.
- R3 verified: the intro is absent from `kickoff_template_manifest()` and the instantiate plan.

*v1.1 — tracks Requirements v0.3. Lessons-hardened (render-only loader replaces manifest binding in
Step 1 / R3). Implemented.*
