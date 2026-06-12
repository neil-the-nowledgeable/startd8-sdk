# View Prose — Implementation Plan (SDK-home)

**Version:** v0.5 (Phase 2 COMPLETE — full key-set shipped; `controls` on `feat/view-prose-controls`)
**Date:** 2026-06-12 (v0.5, v0.4, v0.3, v0.2) · 2026-06-11 (v0.1)
**Status:** Phase 1 + Phase 2a/2b/2c/2d implemented + tested (73 view tests; 142 green across touched
surfaces; generated `routes.py` compiles; CLI e2e + `--check` verified). Full key-set
(title/intro/empty/success/error/controls) ships; no keys reserved. Follow-ups: control help text,
export-format-link labels.
**Pairs with (the "what"):** `strtd8/docs/USER_FACING_CONTENT_REQUIREMENTS.md` §C (FR-PG-10/11/12, OQ-7) —
the consumer-owned contract. This doc is the SDK-home "how" for hand-off item #3.
**Tracked:** `strtd8/docs/SDK_QUICK_WINS_2026-06-10.md` #7.
**Module:** `src/startd8/view_codegen/` (+ `backend_codegen/` drift/header glue).

> **Reading order.** §0 is the code reality this plan rests on (every claim file:line-cited). §1 is the
> one decision that matters — *where prose lives* — and why the requirements' implied answer was wrong.
> §6 is the accidental-complexity ledger (what we opportunistically fix vs. deliberately leave). §8 is
> the reflection that flows back into the requirements.

---

## 0. Code-grounded findings (the reality the plan rests on)

All verified by reading `view_codegen/` + `backend_codegen/` at HEAD.

### 0.1 The parser is already strict — adding a section is well-trodden
- `parse_views()` (`view_codegen/manifest.py:187-456`) is **loud-fail**: unknown view keys → `ValueError`
  (`:216-218`), unknown kind/scope/entity/field/compute-binding all raise. Allowed view key-set is the
  closed `_VIEW_KEYS` (`manifest.py:91-95`).
- Per-archetype key-sets are **already enforced and tight**: `import-flow` allows **only**
  `{name, kind, route}` (`:258-267`); `computed-panel` only `{name, kind, route, compute}` (`:269-285`);
  `rendered-content` only `{name, kind, route, root, content_field, prose_key}` (`:288-312`).
- Precedents for a *new strict section* are uniform and copyable: `parse_ai_passes`
  (`ai_layer.py:155-254`, `_PASS_KEYS`), `parse_pages` (`pages_generator.py:67-123`, `_PAGE_KEYS`),
  `parse_filters` (`filters_manifest.py:26-51`, `_KEYS`), `parse_forms` (`forms_manifest.py:35-72`).
  All raise `ValueError`; CLI catches it centrally (`cli_generate.py:267-271`). Closed-vocabulary
  reject-loud already exists (`parse_forms` `on_create`, `forms_manifest.py:66-70`).

### 0.2 The drift hash is whole-text — "outside the hash on the same file" is NOT free
- Owned files carry a 2- or 3-hash header (`_headers.py`); the hash is `schema_sha256(<entire input>)`
  — a plain SHA-256 of the **full text** (`schema_renderer.py:234-236`). `_check_forms_drift` hashes
  the **whole `views.yaml`**: `schema_sha256(forms_text)` (`drift.py:521`). **There is no
  subset-of-keys hashing anywhere in the codebase.**
- The proven "prose outside the hash" pattern is **architectural separation, not selective hashing**:
  - **pages:** owned shell `app/templates/pages/<name>.html` carries the header + `{% include %}`s an
    **untracked** body fragment `_<name>.body.html` that has **no header** and is re-rendered every
    run (`pages_generator.py:185-217`). Editing the source `.md` only rewrites the fragment → drift
    never trips. Header docstring states this explicitly (`_headers.py:65-85`).
  - **ai-layer:** the per-pass prompt lives in `app/ai/passes/<name>.md`, **read at generate time but
    never hashed** (`ai_layer.py:1-10`).
- **Consequence:** putting a hash-exempt `prose:` block *inside* `views.yaml` would force a new
  `parse-and-hash-only-the-structural-subset` mechanism (strip `prose:`, re-dump, hash) that **exists
  nowhere** and **diverges from every generator**. That is textbook accidental complexity. (See §1.)

### 0.3 The four archetypes render very unevenly — "give all four a title/intro" is not uniform
| Archetype | Renders an HTML page? | Title today | Outcome copy surface |
|---|---|---|---|
| `detail-compose` | **Yes** (`<h1>{v.module}</h1>`, `renderers.py:1053/1063`) | raw `name` | none (display-only) |
| `computed-panel` | **Yes** (`<h1>{v.module}</h1>`, `renderers.py:1071`) | raw `name` | none (display-only) |
| `import-flow` | **Yes** (`<h1>{v.module}</h1>` + 2 forms, `renderers.py:1077-1093`) | raw `name` | **JSON only** — validate/restore return JSON (`renderers.py:892-920`); **no server-side HTML success/error today** |
| `export-package` | **No** — template is a placeholder; routes serve raw JSON/Markdown (`renderers.py:820-837`) | n/a | n/a |

- **import-flow controls** are mostly **anonymous**: `<button>Validate</button>` / `<button>Restore</button>`
  carry **no `id`/`name`** (`renderers.py:1084/1090`). The file inputs (`name="file"`) and confirm
  checkbox (`name="confirm" value="restore"`) **are** stable (`:1083/1087/1088`). The control set is a
  **closed, tiny, per-archetype enum** (import-flow = validate/restore/confirm) — not an open space.
- **export-package has no HTML screen at all** — so FR-PG-11's "title/intro for `/export`" has *nowhere
  to render* without first adding an HTML landing surface to the archetype (new, separable scope).

### 0.6 Two render paths — the prose chrome rides only the template path (R1-S1)
The served HTML is produced by **two** functions the rest of this plan must keep distinct:
- `render_view_template` (`renderers.py:979`) emits `app/templates/views/*.html` — **this** path holds
  the inline `<h1>{v.module}</h1>` chrome blocks the prose feature targets.
- `render_view_module` (`renderers.py:~735`) emits `app/views/*.py` (the Python view module), dispatching
  `_render_import_flow` (`:488`) / `_render_detail_compose_model` (`:219`) / `_render_export_package_model`.
  These build *data/route* code, **not** the served `<h1>`.

**Consequence:** the prose fragment is included by the **template path only**; the dispatched module
functions are **out of scope for Phase 1** (they don't render the title the user sees). This is what makes
S4's "touch only the title/intro/empty lines, not the dispatch/data code" actually verifiable.
Note the `<h1>{v.module}</h1>` f-string occurs at **ten** template sites
(`:966/994/1002/1025/1053/1063/1071/1081/1097/1103`) — the **three Phase-1 archetype** titles are
`:1053` (value-map / model-compose), `:1071` (computed-panel), `:1081` (import-flow).

### 0.4 Real computed values (corrects the v0.4 placeholder vocabulary)
| Archetype | Function | Returns | Real tokens |
|---|---|---|---|
| import-flow validate | `_validate` (`renderers.py:522-547`) | `{valid, errors, counts}` | `{errors}` (list), `{counts}` (per-entity) |
| import-flow restore | `_restore` (`renderers.py:561-584`) | `{imported, total}` | `{imported}` (per-entity), `{total}` (int) |
| computed-panel | `_data` (`renderers.py:341-349`) | `{score, nudges, present}` | `{score}` (0-1), `{present}` (per-entity); `nudges` already rendered |
| export-package | json/markdown (`renderers.py:618-666`) | raw export | **none** (no HTML outcome) |
| detail-compose | `_data` (`renderers.py:238-280`) | per-root list | **none** (display-only) |

- v0.4's vocabulary was wrong in three places: import-flow **success** is `{imported}`/`{total}` (not
  `{counts}`); export-package has **no** `{formats}` token (and no outcome surface); computed-panel is
  `{score}`/`{present}`, there is **no `{total}`**. **Outcome copy (`success`/`error` + any placeholder)
  applies to exactly ONE archetype: import-flow** — and even there it has no HTML rendering surface today.

### 0.5 Pre-existing prose infrastructure (naming-collision flag)
- `view_codegen` **already has a `prose_*` vocabulary** for a *different* thing: the `rendered-content`
  archetype (AR-6) renders an **entity's text column** as HTML via `prose_body`/`prose_preview`/
  `prose_html` (the `_PROSE_MODULE` string, `renderers.py:397-430`), keyed by the existing **`prose_key`**
  view key (`manifest.py:91`). That is *entity-data prose*, not *view-chrome copy*. Overloading the bare
  word "prose" for both is a cognitive-complexity risk (§6, AC-flag-5).

---

## 1. The one decision that matters: where prose lives

**Decision: a separate, strict-parsed `view_prose.yaml`, rendered into untracked fragments — NOT a
`prose:` section inside `views.yaml`.**

This is the essential-complexity choice, and it is forced by §0.2:

| Option | Hash-exemption mechanism | New code | Diverges from existing generators? |
|---|---|---|---|
| **A — `prose:` inside `views.yaml`** | strip `prose:` before hashing → hash structural subset | a *new* subset-hash path nobody else uses | **Yes** — every generator hashes whole text |
| **B — separate `view_prose.yaml` + untracked fragment** *(CHOSEN)* | prose is a *different file*, read at generate time, rendered to a header-less fragment the owned template `{% include %}`s | **zero new hashing code** — reuses the pages mechanism verbatim | **No** — identical to pages + ai-layer |

Option B is also the *consistent* SDK pattern, confirmed by the display layer's own history: **hash-exempt
prose → standalone file; hashed structural config → `views.yaml` sections.** `display.yaml` shipped
**standalone** (not a `views.yaml` section) precisely because the team converged on file-per-lifecycle;
`filters:`/`forms:` are `views.yaml` sections *because they are structural/hashed*. Prose, being
hash-exempt, belongs in its own file by the same rule. This **retires the v0.4 ambiguity** (which named
both `views.yaml prose:` and a parked `prisma/view_prose.yaml`) in favor of the one that costs nothing.

**Rendering mechanism (mirror `pages_generator.py:185-217` exactly):**
1. The **owned view template** keeps its schema+views 2-hash header and its structural body. The
   title/intro/empty slot is **emitted conditionally (R1-S7):** when this view has prose, the generator
   emits an `{% include %}` of the fragment; **when it has none, it emits today's exact literal
   `<h1>{v.module}</h1>` byte-for-byte.** The owned template's *source bytes* are hashed, so the
   no-prose branch MUST be byte-identical to the pre-feature baseline — otherwise every existing app
   trips drift on regen even with no manifest. This means the title line is **not** unconditionally
   refactored to a Jinja `{% block %}` (that would change the source bytes); the include exists only on
   the prose-present branch. (See §6 AC-1, corrected.)
2. The **prose fragment** (`app/templates/views/_<name>.prose.html` — header-less, untracked) is
   rendered from `view_prose.yaml` at generate time and overwritten every run.
3. Editing `view_prose.yaml` rewrites only the fragment → `--check` on the owned template stays green.
   **No prose hash exists at all** (same as ai-layer prompts).
4. **`intro` rendering contract (R1-S8):** `intro` is **markdown → HTML at generate time**, via the same
   `render_markdown` path `pages_generator` uses — so the author experience is consistent (`**bold**`
   works in both `.md` files and inline `view_prose.yaml`). `title`/`empty` render as **escaped literal
   text** (no markup). `view_prose.yaml` is consumer-authored/trusted, so this is not an injection
   surface; the contract is stated only to avoid an inconsistent markdown-vs-literal author experience.

---

## 2. Phasing (sharper than v0.4)

§0.3/0.4 force a cleaner cut than v0.4's "everything but controls is Phase 1":

- **Phase 1 — static chrome, zero substitution, zero new render surface. SHIPPED 2026-06-12
  (`feat/view-prose-phase1`).** Keys `title`, `intro` **only**. Pure text rendered into the untracked
  fragment. Lands on the archetypes that *already render HTML* (detail-compose, computed-panel,
  import-flow). **No placeholder engine, no control ids, no new endpoints.** This is the bulk of the
  user-visible win ("no screen shows a raw machine name").
  > **Implementation finding (§6 AC-2 revised): `empty` is NOT a Phase-1 key.** Building Phase 1 showed
  > `empty` is not uniform — only `detail-compose` has a clean panel-empty literal (`renderers.py:1054`);
  > `computed-panel`'s "All signals met." is a *complete*-state and `import-flow` has no empty surface.
  > And a drift-safe `empty` override must route through its **own untracked fragment** (the literal is
  > inside archetype-specific Jinja, not an inline string). So `empty` **moved to Phase 2**; the shipped
  > parser rejects it loud (reserved-until-built) alongside `controls`/`success`/`error`.
- **Phase 2 — gated on a new render surface (COMPLETE 2026-06-12):**
  - **`empty` — DONE (2a).** No-rows panel state; own untracked fragment `_<name>.empty.html`; model-scoped
    `detail-compose` only (the one clean surface, `:1054`); loud-fail elsewhere. The per-row "not yet
    linked" flag (`:1048`) stays archetype-owned.
  - **`export-package` title/intro — DONE (2b).** Prose-gated HTML landing page (`render_export_landing_template`)
    + a bare HTML route (`render_view_router(..., chrome_views)`); `/export` was a 404. Byte-identical absent.
  - **`success`/`error` — DONE (2c), import-flow RESTORE only.** Server-rendered owned result page
    (`render_import_result_template`) + untracked outcome fragment (`render_view_outcome_fragment`,
    `{token}`→Jinja). Only the restore route changes (template untouched). **Validate stays JSON** ⇒ closed
    set: `success`⊆`{imported}`/`{total}`, `error`⊆`{errors}` (the `{counts}` token was validate-only; dropped).
  - **`controls` — DONE (2d + follow-ups).** Per-control untracked fragment
    (`_<name>.control.<id>.html`); the button/label text becomes an `{% include %}` only for authored
    controls ⇒ byte-identical absent. **R1-S5 caveat RETIRED:** no HTML-id stamping is needed — the
    control-id is the *manifest key* (a closed per-archetype enum), not an HTML attribute — so there is
    **no hashed-template change for apps without controls prose, hence no downstream `--check` bump.**
    Control values accept a `label` string **or** a `{label, help}` mapping (help → a trailing `<small>`
    from its own untracked fragment). **Both control archetypes ship:** import-flow
    (`validate`/`restore`/`confirm`) and the export landing's format links (`markdown`/`json` — controls
    alone also opt the export into its landing). Unknown id / non-supported-archetype / malformed value
    loud-fail. **No keys remain reserved.**

> v0.4 had `success`/`error` in Phase 1. Planning moves them to Phase 2: there is **no HTML surface**
> to render outcome copy into, and they touch exactly one archetype. Shipping title/intro/empty first
> delivers ~all of the visible value with none of the surface-area risk.

---

## 3. Implementation steps (Phase 1)

| # | Step | File(s) | Notes |
|---|---|---|---|
| S1 | `parse_view_prose(text, *, known_views) -> dict[str, ViewProse]` | **new** `view_codegen/view_prose.py` | Copy `parse_pages`/`parse_filters` shape: `ValueError` loud-fail; `_PROSE_KEYS = {"title","intro","empty"}` (Phase 1); reserved set `{"controls","success","error"}` **rejected-loud** until Phase 2 (the `parse_forms` reserved pattern); gate view names against `known_views`. |
| S2 | `ViewProse` dataclass (`title/intro/empty: str|None`) + `__init__` re-export | `view_codegen/view_prose.py`, `view_codegen/__init__.py` | Keep ViewSpec untouched — prose is a *sidecar* keyed by view name, not a field on ViewSpec (preserves the views.yaml hash surface). |
| S3 | Render the untracked prose fragment per view | `view_codegen/renderers.py` (new `render_view_prose_fragment`) | Mirror `render_page_body_fragment` (`pages_generator.py:210-217`): header-less HTML partial, overwritten each run. |
| S4 | Owned templates conditionally `{% include %}` the fragment; **literal-identical when absent** | `renderers.py` **template path** (`:1053`/`:1071`/`:1081` — the 3 Phase-1 archetype `<h1>` sites; §0.6) | **Prose-present:** emit `{% include "views/_<name>.prose.html" %}` for the title/intro/empty slot. **Prose-absent:** emit today's exact `<h1>{v.module}</h1>` byte-for-byte (R1-S7 — do **not** unconditionally Jinja-ify the line; that changes hashed source). Touch only these title/intro/empty sites — not the dispatch (`render_view_module`) or data code (§0.6). |
| S5 | Header kind + drift routing for the owned view templates | `_headers.py`, `backend_codegen/drift.py` | The owned view template already needs a views-hash header; ensure the **fragment** carries none and is excluded from `--check` (no `startd8-artifact` marker — see S7 for the direct gate assertion). |
| S6 | CLI flag `--view-prose prisma/view_prose.yaml` + cap-dev-pipe pass-through | `cli_generate.py` (+ cap-dev-pipe `run-prime-contractor.sh` / generate seam) | Mirror `--pages` end-to-end. **Pipe seam (R1-S6, verify-at-home):** thread `--view-prose` through the same generate-invocation point that already forwards `--pages` in the `--lang python` flow; name the exact seam when implementing (it is the `generate backend/views` call the pipe constructs). Absent ⇒ today's behavior. |
| S7 | Tests | `tests/unit/view_codegen/test_view_prose.py` | parse loud-fail (unknown key, unknown view, reserved key present, **right-token/wrong-archetype** for Phase 2); fragment render; **gate assertions (R1-S4): the fragment is NOT matched by `_HEADER_KIND_RE` (`backend_codegen/drift.py:30`) → `header_kind(fragment) is None` AND `is_owned_view_file(fragment) is False`** — assert the mechanism, not just the symptom; **drift-stability e2e: edit prose → `--check` stays `in_sync`**; **byte-identical-when-absent golden (R1-F4)**: `generate views` with no manifest == pre-feature baseline. |

**Backward-compat invariant (test it — R1-F4/S7):** with no `view_prose.yaml`, every owned **template
source** renders **byte-identical** to today (literal `<h1>{v.module}</h1>`, not a Jinja block) — the
`filters:`/`forms:` "inert when absent" contract (`filters_manifest.py:30-32`). The golden test diffs the
*emitted template bytes*, not just the served app output (R1-S7).

---

## 4. Implementation steps (Phase 2 — gated, listed for completeness)
- P2a: add stable `id`s to import-flow buttons (`renderers.py:1084/1090`), enumerate the closed control
  set, extend `_PROSE_KEYS` with `controls`, render labels from the fragment.
  - **Migration note (R1-S5):** stamping `id`s mutates the **owned template** HTML, which **is**
    drift-tracked. Every existing generated app (strtd8, startd8-generator) will therefore report
    `--check` **`stale` (regenerable), not `tampered`**, on the P2a upgrade — a one-time, expected drift
    bump, not a hand-edit. Call this out in the P2a release note so consumers don't read it as tamper.
- P2b: add an HTML outcome surface to import-flow (render validate/restore result server-side or via a
  small htmx swap), then enable `success`/`error` with the closed placeholder set + a *whitelist*
  substitution (renderer substitutes only known tokens; unknown `{x}` → loud parse error).
- P2c: add an HTML landing template to `export-package` (intro + the two format download links), then
  enable its `title`/`intro`.

---

## 5. Placeholder vocabulary — corrected & closed (for Phase 2)
- **import-flow** — `error`: `{errors}`, `{counts}` · `success`: `{imported}`, `{total}`.
- **computed-panel / detail-compose / export-package** — **no outcome copy, no placeholders.**
- Substitution is a **whitelist** keyed by `(archetype → token set)`; an unknown `{token}` is a loud
  parse error. No general template-eval — just `str.replace` over the closed set. (Essential complexity:
  one archetype, four tokens; do **not** build a substitution engine.)

---

## 6. Accidental-complexity ledger (the user's explicit ask)

**Opportunistically eliminate (we're touching these lines anyway, low risk):**
- **AC-1 — per-view title injection, NOT an unconditional Jinja refactor (corrected per R1-S2/S7).**
  The `<h1>{v.module}</h1>` f-string occurs at **ten** template sites
  (`:966/994/1002/1025/1053/1063/1071/1081/1097/1103`) — earlier drafts of this bullet wrongly listed
  `:1054`, which is the **empty-state literal**, not an h1. The **three Phase-1 archetype** titles are
  `:1053`/`:1071`/`:1081` (§0.6). The cleanup is **conditional**: when a view has prose, its title slot
  becomes a fragment `{% include %}`; **when it doesn't, the line stays the exact `<h1>{v.module}</h1>`
  literal** (R1-S7 — refactoring it to a `{% block %}` unconditionally would change the hashed template
  source and drift every existing app). So the "remove the hardcoded-title smell" win materializes only
  on the prose-present branch — a smaller, safer cleanup than v0.1 claimed.
- **AC-2 — scattered empty-state literals (anchors corrected per R1-S3).** The `empty` prose key targets
  the **panel-level no-rows** literals: "No {root} records yet" (`:1054`, model-compose), "Nothing here
  yet" (`:967/1026`), "All signals met." (`:1074`). It does **NOT** touch the per-row **"not yet linked"**
  flag (`:1048`), which is emitted *inside a populated relation list* when a row has no links — a distinct
  FR-8 display concern that **stays archetype-owned** (parallel to the per-signal-nudge exception). Route
  the panel-empty literals through `empty` **with the current string as the literal default** — no
  behavior change when prose absent, now overridable.

**Deliberately DO NOT touch (flagged for a future, separate pass — touching them now is scope creep):**
- **AC-3 — mixed dispatch** in `render_view_module` (`renderers.py:736-753`): special-cases +
  `_MODULE_RENDERERS` table. A `(kind, scope)` dispatch table would be cleaner, but it is **not on the
  prose path** — refactoring it now adds risk for no prose benefit. *Flag only.*
- **AC-4 — `_PROSE_MODULE` as a baked string literal** (`renderers.py:397-430`): should be a real `.py`
  imported, not a `"\n".join` string. Orthogonal to view-chrome prose. *Flag only.*
- **AC-5 — "prose" overload** (§0.5): existing `prose_key`/`prose_body` (entity-data prose) vs. new
  view-chrome copy. **Mitigation chosen:** the new input is a *separate file* `view_prose.yaml` and the
  new dataclass is `ViewProse` (chrome), keeping the existing `prose_key` (rendered-content) untouched.
  Residual English-overload accepted; **do not** rename the existing `prose_*` helpers (churn for no
  gain). *Documented, contained.*
- **AC-6 — label fallback split** (`renderers.py:972` template chain vs `:247/259` data binding):
  pre-existing inconsistency in the *display* layer, not the prose layer. *Flag only.*
- **AC-7 — test-scaffold duplication** (`renderers.py:1165-1508`): real, but a test-infra refactor, not
  prose. *Flag only.*

**Net:** the prose feature *adds* one small module + one fragment-render path (both copies of proven
patterns) and *removes* the hardcoded-title and scattered-empty-state smells on the exact lines it
touches. It introduces **zero** new hashing, dispatch, or substitution machinery in Phase 1.

---

## 7. Risks
- **R1 — fragment-include must be header-less & marker-less** or `--check`/`is_owned_view_file` will try
  to drift-check it. Mitigation: render with no `startd8-artifact` marker (S5); cover with the
  drift-stability test (S7).
- **R2 — export-package & success/error look like Phase 1 in the requirements but have no render
  surface.** Mitigation: §2 moves them to Phase 2 explicitly; requirements update must match.
- **R3 — naming overload (AC-5)** could confuse future readers. Mitigation: separate file + `ViewProse`
  type + a one-line note in `manifest.py` distinguishing `prose_key` (entity content) from
  `view_prose.yaml` (view chrome).

---

## 8. Reflection → what flows back to the requirements (v0.4 → v0.5)

| v0.4 assumption | Planning discovery | Requirement impact |
|---|---|---|
| Prose is a `prose:` **section of `views.yaml`**, kept outside the drift hash (FR-PG-10/12) | The whole `views.yaml` is hashed (`drift.py:521`); subset-hashing exists nowhere. Hash-exemption is achieved **only** by a separate file + untracked fragment (pages/ai precedent) | **Reframe FR-PG-10/12:** prose lives in a standalone **`view_prose.yaml`**, rendered into an untracked fragment. Drop the "section of views.yaml" framing. Net **less** complexity. |
| `success`/`error` ship in Phase 1 on all four archetypes (v0.4) | Outcome copy is **import-flow-only** and has **no HTML render surface** today; export-package renders **no HTML page** at all | **Re-phase:** Phase 1 = `title`/`intro`/`empty` on the 3 HTML archetypes. `success`/`error` and export-package title/intro → **Phase 2** (each needs a new render surface). |
| Placeholder set: import-flow `{counts}`/`{errors}`, export `{formats}`, panel `{score}`/`{total}` | Real: import-flow success = `{imported}`/`{total}`; export has **no** tokens/surface; panel = `{score}`/`{present}`, no `{total}` | **Correct FR-PG-10** vocabulary; mark it Phase-2 (import-flow only). |
| OQ-7: "can view_codegen expose stable enumerable control_ids?" (open feasibility) | Controls are a **closed tiny enum**, currently anonymous; making them stable is a ~2-line change | **OQ-7 downgrades** from "unknown feasibility" to "known-trivial, sequenced." Resolve it; keep `controls` Phase-2 for *sequencing*, not risk. |
| (not seen) | `view_codegen` already uses `prose_key`/`prose_body` for **entity-data** prose | **Add a non-requirement / note:** new view-chrome prose is a distinct layer; separate file + `ViewProse` type avoids the overload. |
| Strict-parse is a fresh contract to define | Four copyable precedents (`parse_ai_passes`/`parse_pages`/`parse_filters`/`parse_forms`), all `ValueError`, reserved-key reject already exists | **Strengthen FR-PG-10** to name the precedent (`parse_pages` shape) so the contract is unambiguous and the reserved-key Phase-2 gate is a known pattern. |

---

*v0.2 — Post-CRP Round 1 (dual-document review, claude-opus, code-grounded at HEAD). 8 S-suggestions
applied (Appendix A), 0 rejected. Key merges: new §0.6 documents the two render paths so S4's scope is
verifiable (S1); AC-1 anchors corrected — ten h1 sites, `:1054` is the empty literal, Phase-1 titles are
`:1053/1071/1081` (S2); `empty` rebound to the panel-empty literal, not the per-row "not yet linked"
flag (S3); the byte-identical-absence vs Jinja-refactor tension resolved by a **conditional** include
(no-prose branch stays byte-identical) (S7); S7 test now asserts the marker-absence gate directly (S4);
Phase-2 id-stamping flagged as a one-time downstream drift bump (S5); `intro` markdown-rendering contract
stated (S8). Dispositions in Appendix A; round history in Appendix C.*
*v0.1 — Initial plan from `view_codegen/` exploration. Central finding: prose must be a **separate
file rendered to an untracked fragment** (not a `views.yaml` section) — the only hash-exempt mechanism
the codebase supports, and it costs zero new machinery. Phase 1 narrowed to `title`/`intro`/`empty`;
`success`/`error`/`controls`/export-landing moved to Phase 2 (each needs a new render surface).
Placeholder vocabulary corrected against real computed values. Accidental-complexity ledger in §6.*

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
| R1-S1 | Document the two-path render split (template vs module) | R1 (code-verified) | **Applied.** New §0.6 names `render_view_template` (`:979`, holds the `<h1>`) vs `render_view_module` (`:~735`, emits `.py`); prose rides the template path only. | 2026-06-12 |
| R1-S2 | Correct AC-1 anchors (ten h1 sites; `:1054` is empty not h1; Phase-1 = `:1053/1071/1081`) | R1 (code-verified) | **Applied.** §6 AC-1 + §0.6 corrected; S4 step rescoped to the 3 real h1 sites. | 2026-06-12 |
| R1-S3 | `empty` targets panel-empty (`:1054`), NOT per-row "not yet linked" (`:1048`) | R1 (code-verified) | **Applied.** §6 AC-2 anchors corrected; per-row flag declared archetype-owned. | 2026-06-12 |
| R1-S4 | S7 must assert the gate directly (`header_kind is None`, `is_owned_view_file is False`) | R1 | **Applied.** S7 test row now asserts the mechanism vs `_HEADER_KIND_RE` (`drift.py:30`), not just the e2e symptom. | 2026-06-12 |
| R1-S5 | Phase-2 controls id-stamping is a drift bump for existing apps | R1 | **Applied.** §4 P2a migration note: downstream `--check` reports `stale` (regenerable), not `tampered`. | 2026-06-12 |
| R1-S6 | Name the cap-dev-pipe `--view-prose` pass-through seam | R1 | **Applied (partial — verify-at-home).** S6 step now points at the pipe's generate-invocation seam that forwards `--pages`; exact seam to confirm at implementation. | 2026-06-12 |
| R1-S7 | Byte-identical-absence vs Jinja-refactor tension — pick one | R1 (sharpest) | **Applied.** §1 step 1 + S4 + AC-1 reworked: the `{% include %}` is **conditional**; no-prose branch emits today's exact literal (no unconditional `{% block %}`). Golden test diffs emitted template bytes. | 2026-06-12 |
| R1-S8 | State the `intro` markdown-vs-literal rendering/escaping contract | R1 | **Applied.** §1 new step 4: `intro` = markdown→HTML via `render_markdown` (pages path); `title`/`empty` = escaped literal. | 2026-06-12 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none — all R1 S-suggestions accepted; the four code-grounded anchor/mechanism findings were independently verified at HEAD) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus — 2026-06-12

- **Reviewer**: claude-opus (Opus 4.8, 1M)
- **Date**: 2026-06-12 04:10:00 UTC
- **Scope**: Plan quality (S-prefix) + requirements traceability. Code-grounded against `view_codegen/renderers.py`, `manifest.py`, `drift.py`, `backend_codegen/pages_generator.py` at HEAD. Focus: separate-file/untracked-fragment mechanism, Phase 1/2 cut, strict-parse contract, S4 anchor correctness.

**Executive summary**

- **S4's title/intro/empty anchors are split across two render paths the plan never names.** `render_view_template` (`renderers.py:979`) holds the `<h1>{v.module}</h1>` chrome at `:1053/1063/1071/1081` (S4's anchors — correct for the *template*). But the live `/import` and `/value-map` HTML is *also* produced by `render_view_module` → `_render_import_flow` (`:488`) and `_render_detail_compose_model` (`:219`), which are dispatched **around** the inline `_MODULE_RENDERERS` table. The plan should state which path the prose fragment includes into and confirm S4 only needs the template path.
- The `<h1>{v.module}</h1>` f-string appears at **ten** sites (`:966/994/1002/1025/1053/1063/1071/1081/1097/1103`), not the four S4 lists. AC-1 says "repeated at 1053/1063/1071/1081/966/1054" — `:1054` is not an h1 line (it is the "No {root} records yet" empty literal); the four Phase-1 archetypes map to `:1053`(value-map model), `:1071`(computed-panel), `:1081`(import-flow). Tighten the anchor list.
- `detail-compose` has **two** renderers: the model-compose path (`_render_detail_compose_model`, `:219`, used for `/value-map` — has both a panel-empty literal and per-row "not yet linked") and the plain inline block (`:1061`, just `data.root.id` + panels, no empty literal). Plan/AC-2 must say `empty` targets the model-compose panel-empty (`:1053` "No {root} records yet"), not the per-row flag (`:1048`).
- R1 (header-less fragment) leans on `is_owned_view_file`/`startd8-artifact` absence (`view_codegen/drift.py:16`). The plan asserts this but the drift-stability test (S7) should also assert the fragment is **not** matched by `_HEADER_KIND_RE` (`backend_codegen/drift.py:30`) — the actual gate.
- Phase 2 `controls` id-stamping (P2a) changes generated HTML (`<button id=...>`), which **is** drift-tracked on the owned template — so stamping ids is itself a drift-bumping change to existing apps. Not noted as a migration consideration.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Architecture | high | Add a subsection to §0.3 (or a new §0.6) documenting the **two-path render split**: `render_view_module` (`:735`, emits `app/views/*.py` — dispatches `_render_import_flow`@488 / `_render_detail_compose_model`@219 / `_render_export_package_model`) vs `render_view_template` (`:979`, emits `app/templates/views/*.html` — holds the inline `<h1>{v.module}</h1>` blocks S4 targets). State explicitly that prose chrome (title/intro/empty) renders via the **template** path only, so S4's anchors are correct and the dispatched module functions are out of scope for Phase 1. | S4 says "touch only the title/intro/empty lines — not the dispatch or data code", but never establishes that the dispatch functions (488/219) don't also render the title — a reader can't verify S4 is complete without this. Verified: template path owns the served `<h1>`; the module path builds the Python view module. | New §0.6 or expand §0.3 | grep `<h1>{v.module}` → confirm template-path sites; confirm `_render_import_flow`/`_render_detail_compose_model` emit `.py`, not the HTML `<h1>` the user sees. |
| R1-S2 | Validation | high | Correct AC-1's anchor list: `f"<h1>{v.module}</h1>"` appears at `:966/994/1002/1025/1053/1063/1071/1081/1097/1103` (ten sites). AC-1 currently lists "1053/1063/1071/1081/966/1054" — `:1054` is the **empty-state** literal ("No {root} records yet"), not an h1. Scope Phase-1 title conversion to the three live archetypes' h1 sites: `:1053` (value-map/model-compose), `:1071` (computed-panel), `:1081` (import-flow). | A wrong line in the accidental-complexity ledger means the implementer either over-touches (10 sites incl. board/dashboard/workspace not in Phase 1) or edits the empty literal thinking it's a title. | §6 AC-1 bullet | grep the literal; assert the 3 Phase-1 archetype h1 sites are exactly `:1053/1071/1081`. |
| R1-S3 | Data | high | AC-2 / S4: clarify that the `empty` prose key targets the **panel-level** empty literal "No {root} records yet" (`:1053`, model-compose) and "Nothing here yet"/"All signals met." (`:967/1026/1074`) — NOT the per-row "not yet linked" flag (`:1048`), which is emitted inside a *populated* relation list and is a distinct FR-8 display concern. Add a one-line note that per-row "not yet linked" stays archetype-owned (parallel to the per-signal-nudge exception). | The requirements (FR-PG-11) say value-map `empty` "reuses 'not yet linked'", but code shows that string is per-relation-row, not the no-rows empty. If the plan inherits that conflation, the `empty` key will be wired to the wrong literal. | §6 AC-2 + §3 S4 Notes | Render value-map with 0 roots (expect `empty` key) vs roots+unlinked-relations (expect per-row flag unchanged). |
| R1-S4 | Risks | medium | Strengthen S7 drift-stability test to assert the **mechanism**, not just the outcome: the prose fragment file must (a) contain no `# startd8-artifact:` marker (so `_HEADER_KIND_RE`@`backend_codegen/drift.py:30` yields None) and (b) not satisfy `is_owned_view_file`@`view_codegen/drift.py:16`. Assert both directly, in addition to the "edit prose → `--check` in_sync" end-to-end. | R1's mitigation rests on marker-absence, but the plan tests only the end-to-end symptom. A future change that gives `is_owned_view_file` a looser match could re-capture the fragment with the e2e test still green if it doesn't exercise an edited fragment. Test the gate directly. | §3 S7 row + §7 R1 | Unit-assert `header_kind(fragment_text) is None` and `is_owned_view_file(fragment_text) is False`. |
| R1-S5 | Ops | medium | Add a Phase-2 migration note (P2a): stamping stable `id`s on the import-flow Validate/Restore buttons (`renderers.py:1084/1090`) changes the **owned template** HTML, which is drift-tracked. Existing generated apps will therefore report drift / require a regen on the Phase-2 upgrade. State that this is a one-time `--check` bump for downstream apps and is expected (not a tamper). | The plan treats id-stamping as "~2 lines, trivial", but it mutates a hashed surface; downstream consumers (strtd8, startd8-generator) will see drift. Flagging it prevents a false "tampered" reading. | §4 P2a + §7 (new R4) | Regenerate an existing app post-P2a; confirm `--check` reports `stale` (regenerable), not `tampered`. |
| R1-S6 | Interfaces | low | S6 (CLI `--view-prose`): specify the **cap-dev-pipe pass-through** mechanism concretely (which pipe stage/flag forwards `--view-prose`, mirroring how `--pages` is threaded). FR-PG-9 in the requirements asserts pipe-consumability; the plan says "mirror `--pages`" but doesn't name the pipe seam. | "Mirror `--pages`" is under-specified for the pipe leg; without naming the pass-through point the requirements' pipe-consumable AC (FR-PG-9) is untraceable to a plan step. | §3 S6 Notes | Run a cap-dev-pipe `--lang python` pass with a `view_prose.yaml`; confirm the fragment is emitted. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S7 | Risks | medium | The "byte-identical when absent" invariant (after §3) competes with AC-1/AC-2's opportunistic refactor (f-string → Jinja `{% block %}`). Converting `<h1>{v.module}</h1>` to `<h1>{% block vtitle %}{module}{% endblock %}</h1>` changes the **template source text**, which is hashed — so even with no `view_prose.yaml`, the owned template's rendered bytes change vs. the pre-feature baseline, tripping drift for existing apps. Resolve: either (a) the Jinja-slot must render byte-identically (block resolves to the literal, no added markup) and a golden test proves it, or (b) accept a one-time drift bump and document it. Pick one. | This is the central tension: §6 wants to refactor the title lines, §3 promises byte-identical absence. A Jinja block that emits `{% block %}` wrapper text is NOT byte-identical to `<h1>{v.module}</h1>`. The plan asserts both without reconciling them. | §3 invariant + §6 AC-1 | Golden-diff the rendered template (not just app output) pre/post refactor with no manifest; assert empty diff OR documented stale. |
| R1-S8 | Security | low | Phase-1 `intro` accepts "short markdown" rendered into HTML at generate time. Since `view_prose.yaml` is consumer-authored and trusted, this is low risk — but state the **escaping/rendering contract**: is `intro` markdown→HTML (like `pages` `.md` via `render_markdown`) or raw-passthrough? If markdown, note it shares `pages_generator`'s renderer; if a view name or `empty` is rendered raw into an attribute/heading, confirm no injection surface from authored content. | The plan says "mirror `pages_generator.py:185–217`" but `intro` is inline YAML, not a `.md` file — the rendering path (markdown vs literal) is unstated. Settling it avoids an inconsistent author experience (markdown in `.md` but literal in YAML). | §1 rendering mechanism step + §3 S3 | Author `intro: "**bold**"`; confirm rendered as `<strong>` (markdown) or literal per the decided contract. |

**Endorsements**: (none — R1 is the first round; no prior untriaged items.)

---

## Requirements Coverage Matrix — R1

Mapping each requirements section/FR (`USER_FACING_CONTENT_REQUIREMENTS.md` v0.5) to plan coverage. This plan is scoped to **hand-off item #3 only** (View prose §C / FR-PG-10/11/12); FR-PG-1..9 are *other SDK items* (content-pages, form-fix) and are correctly out of this plan's scope — marked N/A (not a gap).

| Requirement Section / FR | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-PG-1 Home/landing page | (out of scope — hand-off #1) | N/A | Other SDK item; not this plan. |
| FR-PG-2 Purpose / how-it-works page | (out of scope — hand-off #1) | N/A | Other SDK item. |
| FR-PG-3 Basic form guidance | (out of scope — hand-off #1/#2) | N/A | Other SDK item. |
| FR-PG-4 Navigation shell | (out of scope — hand-off #1) | N/A | Other SDK item. |
| FR-PG-5 Forms omit system/provenance fields | (out of scope — hand-off #2) | N/A | Other SDK item (form-generator fix). |
| FR-PG-6 `pages.yaml` strict-parse | (out of scope — hand-off #1) | N/A | Other SDK item; the strict-parse precedent it names is reused by this plan's S1. |
| FR-PG-7 MD authored, glue generated | §1 (pages mechanism), §3 S3 | Full | Same untracked-fragment pattern reused. |
| FR-PG-8 Owned + drift-tracked | §3 S5, §7 R1 | Full | Owned template hashed; fragment marker-less. |
| FR-PG-9 Pipe-consumable (`--view-prose`) | §3 S6 | Partial | Plan says "mirror `--pages`" but does not name the cap-dev-pipe pass-through seam (see R1-S6). |
| FR-PG-10 `view_prose.yaml` strict-parse + phased key-set | §0.1, §1, §2, §3 S1/S2, §5 | Full | Precedent (`parse_pages`), `_PROSE_KEYS` Phase-1 set, reserved-loud Phase-2 set, closed placeholder vocab all specified. (Right-token/wrong-archetype clause is an F-suggestion, not a plan gap.) |
| FR-PG-10 Phase 1 keys (title/intro/empty) on 3 HTML archetypes | §2 Phase 1, §3 S1–S7 | Full | — |
| FR-PG-10 Phase 2 (controls / success / error / export title) | §2 Phase 2, §4 P2a/P2b/P2c, §5 | Partial | Listed "for completeness"; each gated on a new render surface. Controls id-stamping drift-migration impact not noted (R1-S5); HTML-outcome-surface design for success/error deferred (acceptable). |
| FR-PG-11 Apply prose to archetypes (acceptance copy) | §2, §3 S4, §6 AC-1/AC-2 | Partial | `/value-map` `empty` anchor conflates per-row "not yet linked" vs panel-empty (R1-S3/F3); `/completeness` per-signal-nudge exception is in the requirements but not echoed in the plan's `empty` wiring; `/export` Phase-2 surface design not yet planned. |
| FR-PG-12 Prose outside drift hash (separate file + untracked fragment) | §1 (decision), §3 S3/S5, §7 R1 | Full | Mechanism fully specified; byte-identical-absence vs. Jinja-refactor tension flagged (R1-S7) but the *requirement* is met by the design. |
| §3 Non-Requirements (no theming/CMS/auth; copy-not-layout) | (respected throughout) | Full | Plan adds no layout/structure changes; consistent with copy-only scope. |
| §5 Hand-off #3 sequencing (3a Phase 1 / 3b Phase 2) | §2, §3, §4, §6 | Full | 3a/3b map cleanly to plan Phase 1 / Phase 2 + AC ledger. |
