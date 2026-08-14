# CRUD List Empty-State — Implementation Plan

**Pairs with:** `CRUD_LIST_EMPTY_STATE_REQUIREMENTS.md` (v0.4)
**Version:** 0.4 (post-CRP-lite R1 — synced to REQ v0.4)
**Date:** 2026-08-14
**Backend:** startd8-python-cascade
**Status:** PLANNED — not implemented. No code changes have been made.

---

## 0. What this plan changed after the reflection pass

| v0.1 plan step | Why it changed |
|----------------|----------------|
| "Add `list_empty_manifest.py` + parser + strict validation + CLI flag" | **Deleted.** `views.yaml` is already threaded into both `render_ui` and `_renderers`; `parse_onboarding` already validates entity keys. Nothing to build (REQ OQ-1). |
| "Introduce `htmx-list-forms` 2-hash kind + register in drift" | **Deleted.** The hash-exempt fragment keeps `list.html` schema-only (REQ FR-3 / Sotto). |
| "Insert copy + CTA under the table" | **Rewritten** as suppress-table-and-render-panel (REQ FR-1). |
| — | **Added** step 4 (`filtered` ctx + no-matches state, REQ FR-5) and step 6 (rollout regen of both dogfood apps, the `--check` blast-radius risk). |

Net effect: the plan lost a module, a manifest, a CLI flag and an artifact kind, and gained one
context key and a rollout step.

## 0.1 What CRP-lite R1 changed (v0.4)

| R1 item | Change |
|---------|--------|
| R1-S1 | Step 6 gains a **fixture prerequisite**: neither dogfood `views.yaml` declares `filters:`, so FR-5 had no harness. The wireframe fixture now declares one filtered entity and one facets-only entity, and §3 Verification exercises them. |
| R1-S2 | Step 5 **loses the `_onb(s)` helper**. `render_list_template` consumes no views.yaml input, so threading the onboarding spec into the `htmx-list` drift renderer was dead plumbing (and an invitation to the 2-hash re-heading Appendix B rejected). Step 5 is now a **negative** parity assertion — zero code. |
| R1-S3 | Step 2 **specifies the filter form's disposition** in each empty branch; it is emitted outside the `<table>` (line 512), so wrapping only the table left it rendering in both. |
| R1-F1 / F2 / F3 (REQ-side) | Step 2 notes the delete-swap boundary (no OOB swap, NR-9); Step 1 `html.escape`s the baked sentence; Step 4 gates the `q` key on a declared non-empty `search:`. |

## 1. Approach

One general rule, applied uniformly: every entity list template gains an `{% else %}` branch that
renders a panel; the panel's sentence comes from an untracked per-entity fragment whose content is
resolved from `onboarding.empty_states` with a deterministic fallback. The owned templates change
once, identically, and never again on a copy edit.

Precedence resolved at generate time (not in the template):

```
onboarding.empty_states[Entity]  →  "No <Title> yet. Add the first one to get started."
```

## 2. Iterations

Each step names its files, the REQ it serves, and its dependencies. The order is acyclic.

### Step 1 — Resolve the sentence (serves FR-2, FR-8) · deps: none

- `src/startd8/backend_codegen/htmx_generator.py`
  - Add a module-private `_empty_state_copy(entity, display, onboarding_spec) -> str`: returns the
    authored `empty_states` value when present, else the deterministic default built from the display
    title (`display.title or entity`, the same resolution `render_list_template` already does at
    line 502).
  - Add `render_list_empty_fragment(entity, display, onboarding_spec) -> str` returning **headerless**
    HTML — one element carrying the sentence only, mirroring `render_form_prose_fragments`
    (`htmx_generator.py:848-879`) which is the established untracked-fragment precedent.
  - **`html.escape` the sentence before it is written into the fragment** (REQ FR-3). The fragment is a
    baked static file, so Jinja's autoescape — which is what protects the checklist path, where the raw
    string rides the ctx (`onboarding_generator.py:53-64`) — never runs on it. Without this, an authored
    `&`, `<` or quote renders escaped on `/welcome` and raw on `/ui/<e>`: a rendered-text divergence and
    a stored-XSS-shaped hole in one. Applies to the deterministic default too (a display title can
    contain an escapable character).
- No parser work: consume `onboarding_manifest.parse_onboarding(forms_text, known_entities=…)`.
  It already raises on unknown entities, so no new validation is needed or wanted.

### Step 2 — Panel in the owned list template (serves FR-1, FR-3, FR-4) · deps: 1

- `htmx_generator.py::render_list_template`
  - Wrap the existing `<table>` block in `{% if items %} … {% endif %}` and add the `{% else %}` panel:
    a `<section class="empty-state">` containing the heading, the unconditional
    `{% include "<e>/_list_empty.html" ignore missing %}`, and the primary CTA anchor to
    `/ui/<e>/new`.
  - Move the existing top-of-page `New <Entity>` link (line 511) inside the `{% if items %}` branch so
    the zero-row state has exactly one create affordance (FR-4).
  - **Filter form disposition — decided, not left to fall out (R1-S3).** `_filter_form_html` is emitted
    *outside* the `<table>` (line 512), so wrapping only the table would leave it rendered in both empty
    branches. The rule: **filtered-empty keeps the filter form** (it is the only way back, and its
    `clear` anchor to `/ui/<e>` at line 485 is the intended escape); **true-empty suppresses it** — a
    facet/search form over an entity with zero stored rows is the same "container with nothing in it"
    cruft FR-1 deletes the `<thead>` shell for, and suppressing it keeps the true-empty panel at exactly
    one affordance (FR-4), with no competing `/ui/<e>` anchor beside the primary CTA.
  - **Delete-swap boundary (REQ FR-1 / NR-9).** The panel is evaluated at full-page render only. The
    delete route keeps returning the flash `<tr>` (`htmx_generator.py:464-465`, `1232-1237`) — do **not**
    add an out-of-band panel swap; deleting the last row leaves the table standing until the next GET.
  - **Invariant to hold:** the include line must name only the entity path, never the copy, and must
    not be gated on whether `onboarding:` exists — that is what keeps the `htmx-list` header honest as
    a schema-only kind. Do **not** add a views-sha to `_tmpl_header` for this kind.
- `htmx_generator.py::render_ui`
  - Parse the onboarding spec once (from the `forms_text` parameter already in scope) and emit
    `app/templates/<e>/_list_empty.html` per entity, appended the same way
    `render_form_prose_fragments` output is appended (line 1452).

### Step 3 — Panel styling (serves FR-7) · deps: 2

- `htmx_generator.py::_BASE_STYLE` — add `.empty-state` rules (card surface, ink-soft sentence,
  emphasized CTA anchor) using the existing FR-FH-11 variables with literal fallbacks. `base.html`
  stays a schema-only `htmx-base` kind; no new stylesheet or static asset.
- Note: the base style currently styles `button` but has no `.button`-style anchor rule, so the CTA
  anchor needs its own rule rather than inheriting one.

### Step 4 — Filtered-empty distinction (serves FR-5) · deps: 2

- `htmx_generator.py::_entity_routes` — in `list_<e>`, for entities with an `EntityFilter`, add a
  computed `"filtered"` key to `ctx`, true iff any **declared facet** key is present and non-empty in
  `request.query_params`, **or** `q` is present and non-empty **and** that entity declares a non-empty
  `search:`. Entities without a filter manifest get `"filtered": False` (or omit it — the template must
  treat undefined as false) so their output is otherwise unchanged.
  - **Do not** derive this from `filters`/`dict(request.query_params)`: that dict carries `created`
    after a PRG redirect and would misreport a just-created-then-empty list as filtered.
  - **Do not** treat `q` as unconditionally declared (R1-F3): `EntityFilter.search` may be empty while
    `facets` is not (`filters_manifest.py:45-50`), and `_list_query_lines` emits the `q` branch only
    `if ef.search` (`htmx_generator.py:1059`). Keying `filtered` off a `q` the query ignores is the same
    lie as the `created` case, through a second door. The condition must stay congruent with the query
    the handler actually builds — derive both from the same `ef.facets` / `ef.search` tuples.
- `render_list_template` — inside the `{% else %}` branch, split on `filtered`: neutral no-matches copy
  plus a clear link to `/ui/<e>` (the filter form's existing `clear` target, line 485) versus the
  onboarding sentence plus the promoted CTA.

### Step 5 — Drift parity (serves FR-6) · deps: 1, 2 · **zero code**

- `src/startd8/backend_codegen/drift.py`
  - **No change.** Step 5 is a *negative* parity assertion (R1-S2): the `"htmx-list"` renderer signature
    at line 275 stays byte-unchanged, because Step 2's invariant means `render_list_template` gains no
    views.yaml input at all. The onboarding spec is consumed only by `render_list_empty_fragment`, whose
    output `--check` never walks.
  - Threading an `_onb(s)` helper in (as v0.2 proposed) would be dead plumbing: a spec passed to a
    renderer that provably cannot use it. Worse, it reads to the next maintainer as evidence that
    `list.html` *does* depend on `views.yaml` — the first step toward the 2-hash re-heading Appendix B
    already rejected. Deleted.
  - No new kind registration. The fragment is headerless, so it is already outside the owned-file set
    that `--check` walks.
  - FR-6 is therefore proved by the FR-3 round-trip already in Step 6 test 3, plus a diff assertion that
    `drift.py` is untouched.

### Step 6 — Tests + dogfood rollout (serves every FR) · deps: 3, 4, 5

- **Fixture prerequisite — do this first (R1-S1).** `tests/fixtures/wireframe/prisma/views.yaml`
  declares **no `filters:` section**, and neither does `household-o11y/prisma/views.yaml`, so as of v0.2
  *no entity in either dogfood target could reach the filtered-empty branch* — the plan's own named
  regression guard would have passed vacuously. Add to the wireframe fixture:
  - `filters: {Profile: {facets: [...], search: [...]}}` — the both-declared entity, which makes the
    `?<facet>=zzz` no-matches case reachable;
  - a **facets-only** entity (`facets:` present, `search:` absent) — which makes the R1-F3 case
    (`?q=zzz` must *not* count as filtered) reachable.

  Two small YAML additions; without them tests 5 and 5b below have no surface to run against.
- `tests/unit/backend_codegen/` — new cases:
  1. zero-row list body contains the panel copy and no `<table>`; one-row body contains the table and
     no panel (FR-1).
     - **1b (R1-F1 boundary):** delete the last row → the response is still the flash `<tr>` (contract
       unchanged, NR-8/NR-9); the subsequent GET `/ui/<e>` shows the panel with no `<table>`.
  2. household-shaped fixture: the `Member` panel's **rendered text** equals the welcome checklist's
     rendered `Member` copy (FR-2); with an `empty_states` value containing `&` and `<b>`, the fragment
     holds the escaped form and the two rendered texts still match (FR-3 escaping).
  3. changing an `empty_states` value changes only the fragment; every owned artifact is byte-identical
     (FR-3) — the round-trip assertion that proves Sotto. Also assert `drift.py` is untouched (FR-6,
     the Step 5 negative assertion).
  4. zero-row body contains exactly one `/ui/<e>/new` href, and the true-empty branch renders no filter
     form (so no competing `/ui/<e>` anchor); the filtered-empty branch does render it (FR-4, R1-S3).
  5. filtered-empty renders no-matches + clear and not the onboarding sentence; `?created=1` alone does
     **not** count as filtered (FR-5) — this is the regression guard for the trap in step 4.
     - **5b (R1-F3 mirror):** on the facets-only fixture entity with zero stored rows, `?q=zzz` shows
       the onboarding sentence, not the no-matches copy.
  6. `views.yaml` with no `onboarding:` section still emits a per-entity fragment with the default
     sentence (FR-8).

  Cases 5 and 5b must **fail before Step 4 lands** — if either passes against the pre-Step-4 tree it is
  asserting nothing.
- `tests/fixtures/wireframe/` — already declares `empty_states` for `Profile` and `Note`, which is the
  harness for FR-2/FR-8 as-is; it needs the `filters:` additions above for FR-5. Regenerate its expected
  artifacts.
- **Rollout (the high risk in the REQ risk table):** the `list.html` change is a one-time structural
  regen for every generated app. In the same pass, regenerate the wireframe fixture and
  `~/Documents/dev/household/household-o11y` (`startd8 generate backend` with its existing
  `--form-prose` / `--human-inputs` flags) and confirm `--check` exits 0 afterward. Apps pinned on
  `--check` without regenerating will report drift — this is expected and correct, and must be called
  out in the PR body.

## 3. Verification

```bash
cd ~/Documents/dev/startd8-sdk
python3 -m pytest tests/unit/backend_codegen -q

# fixture drift parity, with and without an onboarding: section
startd8 generate backend --check   # (wireframe fixture harness) -> exit 0

# FR-5 harness (requires the Step 6 filters: fixture additions)
python3 -m pytest tests/unit/backend_codegen -q -k "filtered_empty or facets_only_q"

# lived dogfood: regen then confirm the orphan is gone
cd ~/Documents/dev/household/household-o11y
startd8 generate backend …         # existing flag set
startd8 generate backend --check   # exit 0
curl -sS http://127.0.0.1:8000/ui/member | grep -c "Add your first household member"   # 1
curl -sS http://127.0.0.1:8000/ui/member | grep -c "<table"                            # 0 while empty
# and the copy is the same string the checklist shows
curl -sS http://127.0.0.1:8000/welcome  | grep -c "Add your first household member"     # 1
```

The last two commands together are the O-2 proof: one authored string, two surfaces. Note the claim is
**rendered-text** identity, not byte identity (REQ FR-2 / R1-F2) — for a sentence containing an
escapable character the grep must be run against the escaped form, since `/welcome` autoescapes at
render and the fragment is escaped at generate time.

## 4. Sequencing note

WIP=1. This is the deferred half of `ONBOARDING_ARCHETYPE_REQUIREMENTS.md` ("Patching every generated
CRUD list template in v1" — its explicit v1 non-goal), so it should land as its own change with the
onboarding archetype already on `origin/main` (PR #463, `1379392`). CRP-lite (one Appendix-C round +
A/B triage) is the S-size default per `BACKEND_ROUTING.md`; offer it before Step 1.

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-S1 | Add an explicit `filters:` fixture prerequisite for FR-5 before Step 6 test 5 | R1 — Composer | Merged into Step 6 as a new first bullet (wireframe gains a both-declared entity and a facets-only entity) and into §3 Verification as a `pytest -k` command. Cases 5 / 5b must fail before Step 4 lands | 2026-08-14 |
| R1-S2 | Delete the `_onb(s)` helper; restate Step 5 as a negative parity assertion | R1 — Composer | Step 5 rewritten to **zero code**: `drift.py:275` byte-unchanged, FR-6 proved by the FR-3 round-trip plus a diff assertion. Rationale kept inline so the deleted plumbing is not re-proposed (it invites the 2-hash re-heading in Appendix B) | 2026-08-14 |
| R1-S3 | Specify the filter form's disposition in each empty branch of Step 2 | R1 — Composer | Decided and written into Step 2: filtered-empty **keeps** the form (its `clear` anchor at line 485 is the way back); true-empty **suppresses** it, keeping exactly one affordance beside the panel CTA (FR-4). Step 6 test 4 extended to assert both | 2026-08-14 |
| R1-F1 / F2 / F3 | Plan-side sync of the accepted REQ items | R1 — Composer (via REQ v0.4) | Step 2 delete-swap boundary note (no OOB swap); Step 1 `html.escape` bullet; Step 4 `q`-gated-on-`search:` bullet; Step 6 cases 1b / 2 / 5b; §3 O-2 note restated as rendered-text identity | 2026-08-14 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — Composer — 2026-08-14

- **Reviewer**: Composer
- **Date**: 2026-08-14 16:30:00 UTC
- **Scope**: CRP-lite, 1 round. Plan-side (S-prefix) review weighted to the sponsor focus: filtered-vs-true empty, table suppression, checklist coherence without a double CTA, `htmx-list` staying 1-hash. Grounded against `htmx_generator.py:471-520` / `1034-1067` / `1106-1126`, `drift.py:191-275`, `filters_manifest.py`, and both dogfood `views.yaml` files.

**Executive summary**

- The plan is accurate where it cites: `render_list_template`'s missing `{% else %}`, the top-of-page `New <Entity>` link at line 511, the `clear` anchor at line 485, and the `drift.py:275` threading all check out as written.
- **Harness gap (highest severity):** Step 6 calls the wireframe fixture "the harness as-is", but `tests/fixtures/wireframe/prisma/views.yaml` declares **no `filters:` section** — and neither does `household-o11y/prisma/views.yaml`. FR-5, the plan's own highest-risk behaviour, has no fixture in either dogfood target, and §3 Verification contains no command that exercises it.
- **Step 5 contradicts Step 2:** if the include line is content-independent and unconditional, `render_list_template` never consumes the onboarding spec, so threading `_onb(s)` into the `"htmx-list"` drift renderer is dead plumbing — and it is the exact coupling that later invites a views-sha into `_tmpl_header`, i.e. the 1-hash regression the focus flags.
- **Unspecified surface:** Step 2 wraps "the existing `<table>` block" but never says what happens to the filter form, which `render_list_template` emits *outside* the table (line 512). Its `clear` anchor is a second `/ui/<e>` affordance sitting next to the panel.
- Ops/rollout is already well covered (Step 6 + the high-priority risk row), so no S-item was spent there.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Validation | high | Add an explicit fixture prerequisite for FR-5 before Step 6 test 5. Step 6 says "the fixture already declares `empty_states` for `Profile` and `Note`, so it is the harness as-is" — true for FR-2/FR-8, false for FR-5: the wireframe fixture has no `filters:` section, and neither does household's `views.yaml`, so no entity in either dogfood target reaches the filtered-empty branch. Declare `filters:` for one wireframe entity (e.g. `Profile` with a facet plus `search:`) and, separately, a facets-only entity so the `q`-not-declared case is reachable. | The `query_params` trap is the plan's own named regression guard ("this is the regression guard for the trap in step 4"), but as written it has no surface to run against — the guard would be written, pass vacuously or not compile, and the trap ships unprotected. Adding the fixture declaration is a two-line YAML change that makes both FR-5 cases executable. | Step 6, as a new first bullet under `tests/fixtures/wireframe/`; and a matching command in §3 Verification | `pytest` case asserting the filtered fixture entity renders no-matches + clear for `?<facet>=zzz`, and the onboarding sentence for `?created=1`; both must fail before Step 4 lands. |
| R1-S2 | Architecture | high | Delete the `_onb(s)` helper from Step 5 and restate Step 5 as a **negative** parity assertion: the `"htmx-list"` renderer signature at `drift.py:275` is unchanged, because `render_list_template` gains no views.yaml input. Step 2's own invariant ("the include line must name only the entity path, never the copy … Do **not** add a views-sha to `_tmpl_header`") means the onboarding spec is consumed only by `render_list_empty_fragment`, which `--check` never walks. | Threading a spec into a renderer that provably cannot use it is dead plumbing that reads, to the next maintainer, as evidence that `list.html` *does* depend on `views.yaml` — which is the first step toward the 2-hash re-heading Appendix B already rejected. Removing it also shrinks Step 5 to zero code and makes FR-6 provable by the FR-3 round-trip that already exists. | Step 5 — replace the first bullet; keep the "no new kind registration" bullet | Assert `drift.py`'s `htmx-list` lambda is byte-unchanged in the diff, and that editing an `empty_states` value leaves every owned artifact byte-identical with `--check` exit 0. |
| R1-S3 | Interfaces | medium | Specify the filter form's disposition in each branch of Step 2. `render_list_template` emits `_filter_form_html` outside the `<table>` (line 512), so wrapping only the table leaves the facet/search form rendered in **both** empty branches. Decide and write down: keep it in the filtered-empty branch (it is the only way back), and either suppress it or state it stays in the true-empty branch — noting that its `clear` anchor to `/ui/<e>` (line 485) is a second navigational affordance adjacent to the panel's primary CTA. | A facet form over an entity with zero stored rows is the same "container with nothing in it" cruft FR-1 deletes the `<thead>` shell for, and leaving the decision implicit means the two dogfood apps will render whatever falls out. It also interacts with FR-4's one-affordance intent, which the plan currently reasons about only for the `New <Entity>` link. | Step 2, alongside the "Move the existing top-of-page `New <Entity>` link" bullet | Test: on a filtered entity with zero stored rows, assert the filter form is absent (or present, per the decision) and that the true-empty body contains exactly one `href="/ui/<e>/new"` and the intended number of `href="/ui/<e>"` anchors. |

**Endorsements & Disagreements**

- None — Appendix C had no prior rounds; Appendices A and B are empty.

---

## Requirements Coverage Matrix — R1

Analysis only (no triage). Requirement sections are taken from `CRUD_LIST_EMPTY_STATE_REQUIREMENTS.md` v0.2.

> **Orchestrator note (v0.4):** left as filed. Every gap in the `Gaps` column was ACCEPTED and closed in
> REQ v0.4 / PLAN v0.4 — see Appendix A in both docs for the merge locations. Re-derive this matrix at R2
> if a second round is run.

| Requirement Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| Overview / Dogfood targets | Step 6 (rollout), §3 Verification | Covered | — |
| O-1 (orientation, one obvious action) | Steps 2, 3, 4 | Partial | The HTMX delete-to-zero transition never re-renders the panel (see R1-F1); O-1 reads as absolute. |
| O-2 (one authored string, two surfaces) | Step 1, §3 Verification (the two `grep -c` commands) | Partial | Byte-identity is asserted but the checklist autoescapes at render while the fragment is baked at generate time (R1-F2). |
| O-3 (zero new sections/flags/kinds) | Step 0 table, Step 5 | Covered | — |
| O-4 (copy edits never trip `--check`) | Step 2 invariant, Step 5, Step 6 test 3 | Covered | Strengthened if R1-S2 lands (the parity claim becomes a negative assertion). |
| Risks — `list.html` structural regen blast radius | Step 6 Rollout bullet | Covered | — |
| Risks — filtered-empty lie | Step 4, Step 6 test 5 | Partial | No fixture declares `filters:` in either dogfood target (R1-S1). |
| Risks — scope creep / third copy home / cost | Step 0 table, Step 5 | Covered | — |
| Risks — panel echoes author copy into HTML | (none) | Gap | No plan step escapes the authored sentence when writing the fragment (R1-F2). |
| FR-1 — panel replaces header-only table | Step 2 | Partial | Filter form disposition unspecified (R1-S3); delete-swap boundary unstated (R1-F1). |
| FR-2 — copy forwarded from `onboarding.empty_states` | Step 1 | Covered | — |
| FR-3 — hash-exempt Words seam (Sotto) | Step 2 (invariant), Step 6 test 3 | Covered | — |
| FR-4 — one create CTA in the panel | Step 2 (move line 511), Step 6 test 4 | Partial | The filter form's `clear` anchor is a second `/ui/<e>` affordance not counted (R1-S3). |
| FR-5 — filtered-empty is a distinct state | Step 4, Step 6 test 5 | Partial | No harness (R1-S1); `q` treated as always declared (R1-F3). |
| FR-6 — drift parity | Step 5 | Partial | Step 5's `_onb` threading contradicts Step 2's invariant (R1-S2). |
| FR-7 — panel styling reuses FR-FH-11 tokens | Step 3 | Covered | Step 3's note about the missing `.button` anchor rule is a good catch. |
| FR-8 — deterministic default, inert-safe | Step 1, Step 6 test 6 | Covered | — |
| Non-goals NR-1..NR-8 | Step 0 table, Step 4 | Covered | R1-F1 proposes an NR-9 (no OOB panel swap on delete). |
| Owned fields | Step 1 (consume `parse_onboarding`) | Covered | — |
| Contract projection (artifact-kind table) | Steps 2, 3, 4, 5 | Covered | — |
