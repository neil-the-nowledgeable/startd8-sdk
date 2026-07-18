# Audience & Content Layer — Requirements (speaking the app to its non-technical author)

**Version:** 0.6 (Draft — CRP R1+R2 triaged & applied; /frontend-design UI/UX pass)
**Date:** 2026-07-18
**Status:** Draft
**Concept key:** `FR-AUD` (Audience). The axis is **(role × fluency)**; values are populated incrementally.
**Primary persona:** the **non-technical app author** — the person the app is *for*, who knows nothing
about the SDK and must never need to. Secondary: the architect + other delivery roles (populated later).

**Builds / reuses (cite, do not restate — Mottainai):**
- The adopted-but-unbuilt **`audience` field on descriptive records** — `DESCRIPTIVE_LAYER_REQUIREMENTS.md`
  FR-DL-1 / R1-F1 (this spec *builds* it; widens `human`/`agent` → the `(role × fluency)` axis).
- The **resolver pattern + byte-identical-default guarantee** — `src/startd8/concierge/audience.py`
  (`KickoffAudience`, the flag→project→global→default ladder, unset ⇒ Intermediate ⇒ byte-identical).
  Reused as *precedent*; NOT overloaded (its axis is kickoff-walk fluency, a different concern).
- The **role taxonomy** — `docs/capability-index/*.yaml` `audiences:` + the FR-J delivery roles (architect,
  BA, PM, backend, …). The `role` half of the axis draws its values from here.
- The **DOES / WON'T / LIVES framing** — `dev-os/NODE-SCHEMA.md` (`does`/`wont`/`lives`) + the
  requirements-preview capability (`kickoff/README.md`).
- The **first consumer** — the wireframe-visual HTML (`WIREFRAME_VISUAL_REQUIREMENTS.md`, FR-WV).

---

## 0. Planning Insights (Self-Reflective Update)

> Grounded against the three real "audience" abstractions in the tree (not an assumed one):

| v0.1 Assumption | Grounding Discovery | Impact |
|---|---|---|
| One audience abstraction exists to extend | **Three** do: fluency (`concierge/audience.py`, built), role (`capability-index` `audiences:`, built-as-data), and the FR-DL-1 record `audience` field (adopted, unbuilt) | FR-AUD builds the **record field** and keys it on **role × fluency**; it reuses the concierge *pattern* but does not overload its enum (would be the overloaded-term anti-pattern). |
| Need a new resolver | `concierge/audience.py` already has the precedence ladder + the byte-identical-default invariant | FR-AUD-3 mirrors that ladder; unset ⇒ architect base ⇒ byte-identical (no regression to the terminal). |
| End-user text is a translation of architect text | The two serve different *questions* — architect: "is the contract right?"; end-user: "is this the app I pictured, and what must I supply?" | FR-AUD-C2 defines a distinct **DOES / WON'T / NEED** framing, not a reworded architect line. |
| Content can be LLM-generated per project | The wireframe is deterministic $0 no-LLM (Hitsuzen); an LLM preview would break byte-identity + trust | FR-AUD-C5: end-user narration is **authored per section**, filled with the user's real data — never model-written. |
| The layered axis is free | Two axes = real authoring + maintenance cost (the user accepted this trade) | FR-AUD-1/NR-1: the axis MUST degrade to base when a `(role,fluency)` cell is absent; you author only the cells you need, when you need them. |

**Resolved open questions:**
- **OQ-A → role × fluency, sparse.** The schema supports both axes but requires neither cell; resolution
  degrades (role,fluency) → (role,·) → base. You never author a full matrix.
- **OQ-B → HTML defaults to `(end_user, intermediate)`; terminal to base (architect).** Unset everywhere ⇒
  today's architect text, byte-identical.

### 0.1 Lessons-Learned Hardening (v0.3)

- **[Overloaded-term co-location]** — did NOT extend `concierge.KickoffAudience` (kickoff-walk fluency) to
  carry reader-role; FR-AUD owns its own `(role, fluency)` key so two meanings don't stack in one enum.
- **[Single-source vocabulary ownership]** — the end-user *words* live in the descriptive manifest (one
  home), audience-keyed; the renderer holds none. The role list is owned by the capability-index/FR-J set
  and cited, not re-enumerated.
- **[Phantom-reference audit]** — `concierge/audience.py` symbols, FR-DL-1 `audience`, the `audiences:`
  keys, and NODE-SCHEMA `does`/`wont` were all grep-verified (see §Reference-Audit).
- **[CRP steering]** — least-reviewed = this doc. Settled: role × fluency axis; abstraction-first; authored
  (no-LLM) content; byte-identical default; reuse (not overload) the concierge pattern.

### 0.2 Design-Principle Hardening (v0.3.1)

> The layered axis the sponsor chose is where accidental complexity could enter — this section is load-bearing.

- **[Accidental-Complexity — the guard]** — a `(role × fluency)` matrix is justified **only** because it is
  *sparse + degrading*: an absent cell costs nothing and falls back to base, so the machinery never forces a
  full matrix and the default path is unchanged. If authoring a variant ever requires touching the resolver,
  the abstraction has failed — variants are pure data. **No new gate, no enum overload, no per-role code.**
- **[Hitsuzen]** — the end-user narration is authored + data-filled, never LLM-derived; determinism (FR-WV-6)
  and $0 are preserved.
- **[Mottainai]** — builds the *adopted* FR-DL-1 field and reuses the concierge ladder; regenerates neither.
- **[Genchi Genbutsu]** — end-user content names the user's **real** data (their record/field names), not
  generic placeholders; omission-surfacing (FR-AUD-C3) reflects the actual plan, never a fabricated gap.
- **[Context-Correctness-by-Construction]** — a requested `(role, fluency)` that isn't authored resolves to a
  defined fallback (never a blank/None narration); the resolver returns the base, always populated.

---

## 1. Problem Statement

The wireframe-visual can now *show* the structure — which makes the language problem obvious. Every word is
**architect voice**: "the DATA MODEL bookend," "31 entities · 155 CRUD routes," "AI passes," "schema.prisma."
The primary viewer is a **non-technical author** who should approve *what they're building* without learning
any of that. And no AI app-builder on the market walks an author **through the construction first** — so
authors discover missing fields, unwritten content, and "obvious once I saw it" gaps only *after* the build.
This layer makes the preview an **introduction to what's being built**, in the author's own language, early
enough to catch those gaps at requirements cost.

| Component | Current State | Gap |
|---|---|---|
| Section narration | architect voice only (`descriptive.yaml`) | no non-technical variant |
| Audience selection | none in the descriptive layer | can't ask for an end-user (or other-role) voice |
| Expectation-setting | "what it does" only | no "what we WON'T build" / "what you must PROVIDE" |
| Omission-surfacing | fields shown, gaps implicit | the author isn't *told* what's missing / needs input |

## 2. Requirements — the abstraction

- **FR-AUD-1 — Audience-keyed record variants (role × fluency).** A descriptive record MAY carry an
  `audience` map providing `what`/`why`/`do`/`next`/`wont`/`need`/`title` variants keyed by `role` and,
  optionally, `fluency`. **Sparse + degrading:** resolution is `(role, fluency)` → `(role, ·)` → **base**
  (top-level fields = architect/intermediate). An absent cell is never an error. Keyed on the unit's stable
  key, not its label. (Builds FR-DL-1.)
  **Authored-variant self-containment (R1-F3):** when a role variant *is* authored, a field it doesn't
  provide resolves to **empty**, NOT the architect base — so a partial `end_user` variant can never leak
  the technical voice into one field. Only an **un-authored** role degrades wholesale to base; fluency
  still inherits its own role's fields.
- **FR-AUD-2 — Defaults preserve today.** Unset role/fluency ⇒ base ⇒ **byte-identical** terminal output.
  The wireframe-visual HTML requests `(end_user, intermediate)`; the terminal `--describe` stays base (architect).
- **FR-AUD-3 — Resolver mirrors the concierge ladder, distinct axis.** `describe(section, plan, *, role,
  fluency)` resolves per FR-AUD-1; a project/global default MAY be set via the same flag→project→global→default
  precedence `concierge/audience.py` uses — but on `FR-AUD`'s own key, never by overloading `KickoffAudience`.
- **FR-AUD-4 — Audience is a *rendering* choice over invariant data (reader-visibility, R1-F2/F7).** The
  plan JSON, the item *set*, statuses, counts, and mockup structure are identical across audiences (the
  view-model carries the architect data verbatim). What audience changes is what is *rendered*: the
  `end_user` surface shows the audience narration/titles + plain band, **hides the raw item `detail`, and
  hides items flagged `technical`** (labels carrying FR-AUD-C1 jargon, e.g. "FastAPI app", "endpoints").
  **Testable rule:** every string rendered in the `end_user` view MUST pass the FR-AUD-C1 ban (§FR-AUD-C1,
  enforced by the banned-word acceptance test).

## 2b. Requirements — the end-user content (what the words must do)

> These define the CONTENT to be authored (the prose lands next pass; here is the bar it must clear).

> **Framing principle (R2-F8).** Every `end_user` string serves the *author's goal* — help them
> **approve, curate, or supply** — never a narration of the tool's own steps. Copy is benefit-first and
> **actionable** (tell them *what to do and why*), not process-descriptive.

- **FR-AUD-C1 — Plain language, zero SDK jargon.** The `end_user` voice MUST avoid implementation vocabulary:
  no *entity, CRUD, schema, prisma, AI pass, manifest, cascade, FastAPI, endpoint, foreign key*. Speak the
  author's domain: *the things your app keeps track of, the pages people visit, the forms they fill in, the
  parts the computer fills in for you*. Enforced by the banned-token acceptance test (R1-F7).
- **FR-AUD-C1b — No process-meta (R2-F1).** Distinct from the jargon ban: the `end_user` surface MUST NOT
  render **tool/process meta** — absolute or relative **filesystem paths**, internal identifiers, or
  **build-pipeline framing** ("we're about to build", "before a single line of code", "$0 / no-LLM /
  deterministic generation"). Show the app's *own name*, not its path. Enforced by a path + phrase
  acceptance check on the rendered surface.
- **FR-AUD-C2 — The DOES / WON'T / NEED framing.** Each section's end-user narration answers three questions,
  not one: **DOES** — what you're getting; **WON'T** — what this deliberately does *not* include (set
  expectations, prevent silent surprise); **NEED** — what *you* must provide (content to write, fields to
  confirm, decisions to make). (DOES/WON'T map to NODE-SCHEMA `does`/`wont`.)
  **NEED is a computed floor the author augments (R1-F1, resolves OQ-AUD-3):** NEED MUST include, at a
  minimum, the **plan-derived gaps** — items the plan itself flags `not_defined`/`placeholder`/`invalid`
  (surfaced as the `need_items` list) — with authored prose layered on top. Authored text alone can
  silently under-report an omission; the computed floor cannot, since it reads the actual plan.
- **FR-AUD-C3 — Surface omissions, don't imply them (scoped, R2-F3/F4).** Two kinds of gap, honestly
  distinguished: (a) **modeled-but-incomplete** — items the plan flags `not_defined`/`placeholder`/`invalid`
  — are surfaced *automatically* under NEED (the computed floor, FR-AUD-C2); (b) **unmodeled** wants — a
  thing the author expected that was never captured at all — have **no plan node and cannot be shown**, so
  the surface MUST instead *prompt* for them: a standing, audience-agnostic closing question ("Is anything
  you expected **not here at all**?"). Framed as an **invitation to confirm completeness**, never a warning
  (R2-F9) — on a zero-gap plan it reads "if it all looks right, you're ready," not "you missed something."
  The doc MUST NOT claim the tool *detects* unmodeled gaps.
- **FR-AUD-C4 — An introduction, not a report.** The top of the surface frames the review task for a
  first-time viewer in **benefit-first, actionable** terms — *what to do and why* (a headline + plain lead +
  a short "what to do" list) — before any counts or sections. It MUST NOT narrate the tool's process (C1b).
- **FR-AUD-C5 — Authored + data-filled, deterministic.** End-user narration is authored per section and
  filled with the author's **real** names (their record types, their field labels), never LLM-generated and
  never generic placeholders. $0, no-LLM, byte-stable (FR-WV-6 preserved).

## 3. Non-Requirements

- **NR-1 — Not a full matrix.** We author only the cells we need (start: `end_user` base fluency + the existing
  architect base). Other roles/fluencies are added on demand; absent ones degrade.
- **NR-2 — Not auto-translation.** No LLM rewrites architect→end-user; the end-user voice is authored.
- **NR-3 — Not a terminal change.** `--describe`'s default stays architect/base (byte-identical).
- **NR-4 — Not a re-spec.** Does not redefine the descriptive layer, NODE-SCHEMA, or the concierge audience
  module — it builds FR-DL-1 and reuses the rest.
- **NR-5 — Not hi-fi / not content generation.** Surfaces what's planned + what's missing; never writes the
  app's real content for the author.
- **NR-6 — Accessibility: a *baseline* is in scope, a full audit is not (R2-F6).** The render MUST meet a
  minimal bar — semantic landmarks (`header`/`main`/`section`/`footer`, headings), a `lang` attribute,
  keyboard-operable disclosure (native `details`/`summary` + visible focus), AA-ish contrast, and
  `prefers-reduced-motion` respect. A full WCAG audit / screen-reader certification is deferred.
- **NR-7 — Internationalization is deferred, but cheap by construction (R2-F7).** Authored strings are
  English-only for now. Because the words live single-sourced in `descriptive.yaml` (the renderer holds
  none — §0.1), locale variants are a low-cost future hook (Mottainai — the externalization cost is already
  paid); this is an explicit *decision*, not an oversight. No i18n machinery is built now.

## 4. Open Questions

- **OQ-AUD-1 — Fluency values for reading.** ✅ RESOLVED — reuse `beginner/intermediate/advanced` (concierge
  labels), avoiding a second vocabulary. Default `intermediate`.
- **OQ-AUD-2 — Where do project/global audience defaults live?** ✅ RESOLVED (v0.4) — a `--audience`/`--fluency`
  flag on `--html` now; a `build-preferences.yaml` project pref is a future add if wanted.
- **OQ-AUD-3 — NEED as data vs prose.** ✅ RESOLVED (R1-F1, v0.5) — NEED is a **computed floor** (the
  plan-derived `need_items`: `not_defined`/`placeholder`/`invalid` items) with authored prose on top; see
  FR-AUD-C2. Remaining sub-question deferred: whether to add *per-field* content-coverage % into NEED beyond
  the summary band.

## Reference-Audit (all verified 2026-07-18)

| Symbol / asset | Owner | Exists? |
|---|---|---|
| `KickoffAudience`, `resolve_audience_preference`, `disclosure_tier`, byte-identical-default | `concierge/audience.py` | ✅ built |
| record `audience` field (human/agent), R1-F1 adopted | `DESCRIPTIVE_LAYER_REQUIREMENTS.md` FR-DL-1 | ✅ spec, ⬜ unbuilt (this builds it) |
| `audiences:` role keys (sdk_architect, workflow_user, …) | `docs/capability-index/*.yaml` | ✅ built-as-data |
| `does` / `wont` / `lives` framing | `dev-os/NODE-SCHEMA.md` | ✅ |
| `describe(section, plan)` / `describe_summary` (extend with role/fluency) | `wireframe/describe.py` | ✅ |
| wireframe-visual HTML consumer (FR-WV) | `WIREFRAME_VISUAL_REQUIREMENTS.md` | ✅ built |

---

## 5. Build status (2026-07-18)

**Abstraction + content both shipped** (full suite 148 pass; terminal `--describe` byte-identical):

- **FR-AUD-1..4 ✅** — `_variant()` (role,fluency)→(role,·)→base resolver; `describe`/`describe_summary`/
  `compose`/`render_html` thread `role`/`fluency`; default = base (byte-identical); HTML = `(end_user, intermediate)`.
- **FR-AUD-C1..C5 ✅ (content authored)** — end_user variants for **all 10 sections + the summary**, each
  carrying the **DOES / WON'T / NEED** framing (`what` / `wont` / `need`) + a friendly `title` + plain
  `do`/`next`. `why` is skipped in the end_user render (its base value is architect voice). No jargon.
- **Gap-3 decision (FR-AUD-4 boundary):** *presentation* strings get an audience form — section **titles**
  (audience `title` override) + the summary **band** (plain labels Health/Size/Content/Ready + deterministic
  `plain_shape`/`plain_status`/`plain_content`). *Data* strings stay data, but the end_user HTML **hides the
  raw item `detail`** (`fields: … | omitted …`) when a mockup already shows it — the visual is the plain form.
- **Verified live on strtd8** (chrome-devtools, 0 console errors): band + titles + section framing all render
  in plain language; un-authored *roles* still degrade to base (sparse invariant holds).
- **Fluency axis ✅ (OQ-AUD-1 resolved: reuse beginner/intermediate/advanced).** Authored for the
  **`end_user` role ONLY** (single-role, per sponsor) on the highest-depth-value spots — `forms` +
  `entities` (full framing) + the `summary` intro. Default `intermediate` = the standard content
  (unchanged); `beginner` = fuller/with-analogy, `advanced` = terse. Other roles ignore fluency;
  un-authored sections degrade to the end_user standard. Zero new machinery — the `_variant` resolver
  already handled `(role,fluency)`.
- **CLI flags ✅ (OQ-AUD-2 resolved).** `wireframe --html <path> [--audience end_user|architect]
  [--fluency intermediate|beginner|advanced]` — scoped to `--html`; unknown values degrade to base.
  Verified live on strtd8: all three depths + the architect voice render (0 console errors).
- **Residual (next):** the `Ready to build?` value is lightly technical; fluency is authored on 3 spots
  (extend on demand — sparse invariant).

### 5.1 CRP R1 triage applied (v0.5, 2026-07-18)

All 9 R1 suggestions actioned (dispositions in Appendix A/B); **153 tests pass, terminal `--describe`
byte-identical, live-verified on strtd8 (0 console errors, 0 banned jargon in the rendered surface)**:

- **R1-F1/F5 — computed NEED floor + falsifiable omission test.** `need_items` (plan-flagged gaps) renders
  under NEED; a mutation test asserts a schema-only project surfaces a gap and a fully-planned section does not.
- **R1-F3 — architect-leak closed generally.** Authored-variant self-containment (FR-AUD-1); no field falls
  back to the technical voice.
- **R1-F6 — empty-project false reassurance fixed.** `_plain_status` reads "still looks empty" at zero; edge table tested.
- **R1-F7 (+F2) — jargon ban is now enforced.** Single-source `has_jargon` matcher; `technical` items (FastAPI/
  endpoints/…) hidden from the end_user render; acceptance test asserts zero banned tokens on the rendered surface.
- **R1-F4 — completeness bar.** Test asserts every section carries end_user DOES/WON'T/NEED (user-ready).
- **R1-F8 — OQ-AUD-3 reconciled** with §5 (closed above). **R1-F9 — byte-identity anchor** documented (test
  `test_default_audience_is_byte_identical_base` + the committed `--describe` shasum gate).
- **R1-F2 (partial-reject):** item *labels* keep the user's real record names (FR-AUD-C5) rather than an
  audience rename; the reader-visibility rule + technical-item hiding covers the jargon concern instead.

### 5.2 CRP R2 triage applied (v0.6, 2026-07-18) — with the `/frontend-design` UI/UX pass

R2 (10 suggestions) triaged (Appendix A). Most landed together with a UI redesign of the preview
("warm editorial blueprint"). **154 tests pass; terminal `--describe` byte-identical; live on strtd8
(0 console errors, 0 jargon, 0 process-meta on the rendered surface):**

- **R2-F1 — process-meta ban (FR-AUD-C1b).** Absolute path replaced by the app's own name; `WIREFRAME_META`
  is architect-only; acceptance test asserts no path / build-pipeline phrasing reaches the end_user.
- **R2-F2/F8 — benefit-first, actionable framing.** New `§2b` framing principle (approve/curate/supply); the
  tool-narration intro replaced by a headline + plain lead + a 3-step "what to do" list (authored, fluency-varied).
- **R2-F3/F4/F9 — omission claim scoped + unmodeled-wants prompt.** FR-AUD-C3 now distinguishes
  modeled-incomplete (auto-surfaced) from unmodeled (prompted), with a closing confirmation framed as invitation.
- **R2-F5 — progressive disclosure.** Collapsed sections; each header shows a status dot + one-liner + a
  "N needs you" chip / "✓ looks set"; narration leads with What-you-get then the highlighted NEED.
- **R2-F6/F7 — a11y baseline in scope (NR-6), i18n deferred (NR-7).** Semantic landmarks, `lang`,
  focus-visible, reduced-motion, AA-ish contrast shipped; i18n noted as a cheap future hook.

---

*v0.6 — CRP R2 triage + /frontend-design UI/UX pass (§5.2): process-meta ban, benefit-first intro, scoped*
*omission claim + unmodeled-wants prompt, progressive disclosure, a11y baseline.*
*v0.5 — CRP R1 triage applied (§5.1): computed NEED floor, leak fix, jargon-ban enforcement, empty-project fix.*
*v0.4 — Abstraction + end-user content both built (§5). Grounded on the three real audience abstractions.*
*v0.3.1 — Post planning + lessons + principle hardening. Grounded on the three real audience abstractions.
Builds the adopted FR-DL-1 field as a sparse, degrading (role × fluency) axis; reuses the concierge ladder +
byte-identical-default; defines the end-user DOES/WON'T/NEED content bar. Abstraction-first (this pass);
end-user prose authored next pass. Ready for CRP.*

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
| R1-F1 | NEED = computed floor + authored | CRP R1 | `need_items` (not_defined/placeholder/invalid) added to the view-model + rendered under NEED; FR-AUD-C2 updated; resolves OQ-AUD-3 | 2026-07-18 |
| R1-F3 | Close the per-field architect leak generally | CRP R1 | `_variant` authored-variant self-containment (missing field ⇒ empty, not base); FR-AUD-1 updated | 2026-07-18 |
| R1-F4 | end_user completeness bar as a gate | CRP R1 | `test_end_user_role_complete_across_all_sections` (all sections have DOES/WON'T/NEED); §5.1 | 2026-07-18 |
| R1-F5 | Falsifiable omission-catching test | CRP R1 | `test_computed_need_surfaces_plan_gaps` (schema-only ⇒ gap; full ⇒ none) | 2026-07-18 |
| R1-F6 | plain_* edge cases / empty-project | CRP R1 | `_plain_status` empty guard ("still looks empty"); `test_plain_summary_edge_cases` | 2026-07-18 |
| R1-F7 | Automated jargon-ban check | CRP R1 | single-source `has_jargon`; `technical` items hidden from end_user; `test_end_user_rendered_surface_has_no_banned_jargon`; FR-AUD-4 reworded | 2026-07-18 |
| R1-F2 | FR-AUD-4 reader-visibility rule | CRP R1 | *(partial — the rule)* FR-AUD-4 now: every end_user-rendered string obeys FR-AUD-C1; raw detail + technical items hidden. Label-rename half → Appendix B | 2026-07-18 |
| R1-F8 | Reconcile OQ-AUD-3 with §5 | CRP R1 | OQ-AUD-3 marked resolved; §5.1 | 2026-07-18 |
| R1-F9 | Pin the byte-identity anchor | CRP R1 | Documented: `test_default_audience_is_byte_identical_base` + committed `--describe` shasum gate (7d1b212…) | 2026-07-18 |
| R2-F1 | Process-meta ban (paths, build-pipeline framing) | CRP R2 | FR-AUD-C1b added; `app_name` replaces path; `WIREFRAME_META` architect-only; `test_end_user_surface_has_no_process_meta` | 2026-07-18 |
| R2-F2/F8 | Benefit-first, actionable framing + principle | CRP R2 | §2b framing principle; intro → headline/lead/steps (authored, fluency-varied); FR-AUD-C4 reworded | 2026-07-18 |
| R2-F3 | Scope the omission claim to modeled-incomplete | CRP R2 | FR-AUD-C3 rewritten (modeled vs unmodeled); §1 claim no longer implies detecting unmodeled gaps | 2026-07-18 |
| R2-F4/F9 | Unmodeled-wants prompt, framed as confirmation | CRP R2 | Summary `closing` ("is anything NOT here at all?… if it all looks right, you're ready"); rendered as end_user footer | 2026-07-18 |
| R2-F5 | Progressive disclosure / cognitive load | CRP R2 | Redesign: collapsed sections, per-header "N needs you"/"✓ looks set", ordered narration (get→need→won't→check) | 2026-07-18 |
| R2-F6 | Accessibility posture | CRP R2 | NR-6 (baseline in scope): landmarks, `lang`, focus-visible, reduced-motion, contrast — shipped in the redesign | 2026-07-18 |
| R2-F7 | i18n posture | CRP R2 | NR-7 (deferred; single-home strings make it cheap) | 2026-07-18 |

*(R2-F9/F10 were the adversarial pass; F9 — frame the unmodeled-wants prompt as confirmation, not warning — is folded into the R2-F4/F9 row above. Any residual R2 item remains in the Appendix C R2 block for a later pass.)*

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| R1-F2 (label-rename half) | Give item labels (`X create/edit form`) an audience `title`-style override | CRP R1 | Item labels are the user's **real record names** (Profile, Company, …) — FR-AUD-C5 mandates keeping real names, not renaming them. The genuine jargon (FastAPI/endpoints infra labels) is handled by hiding `technical` items (R1-F7), and non-technical labels carry no banned tokens. An audience label-rewrite would also make the item *set* audience-varying, muddying FR-AUD-4. Accepted the reader-visibility *rule*; rejected the label rewrite. | 2026-07-18 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-07-18

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-18 (UTC)
- **Scope**: Single-document requirements review (FR-AUD). Weighted to the 6 sponsor focus asks; honors the SETTLED list (role×fluency axis, single-role fluency, authored no-LLM, byte-identical default, reuse-not-overload concierge, sparse-degrading). No prose rewrites; no triage.

##### Focus-ask answers (address before F-suggestions)

**Ask 1 — Is DOES / WON'T / NEED the right content model, and should NEED be partly computed (OQ-AUD-3)?**
- **Summary answer:** Yes on the model; **partial** — NEED should be a *computed floor* the author annotates, not either/or.
- **Rationale:** The product thesis in §1 ("catch missing form fields / unwritten content / obvious-once-seen gaps at requirements cost") is an *omission-detection* claim, but FR-AUD-C2's NEED is authored ("the author's to-do") while FR-AUD-C3 already demands omissions be *explicit* ("forms name what they do **not** collect; content sections name what is **unwritten**"). §5 shows the plan-derived signals already exist and flow: `_plain_status` reads `not_defined`/`placeholder`/`invalid` counts and `_plain_content` reads `content_coverage` ("About {pct}% of the words are written"). An author-only NEED can silently *miss* a gap the plan already knows about — the exact failure the thesis exists to prevent (Mottainai: the data is in hand and being discarded for the NEED field).
- **Assumptions / conditions:** `content_coverage`, `status_counts`, and per-field confirmation state are available per-section at compose time (grounded for the summary band; per-section availability is an assumption).
- **Suggested improvements:** See R1-F1 (computed NEED floor + author-augment), R1-F5 (acceptance test).

**Ask 2 — Is the FR-AUD-4 data-vs-presentation boundary drawn right (titles/band = presentation; labels/detail = data)?**
- **Summary answer:** **Partial** — the boundary is coherent but under-specified where it matters most (item *labels*), and §5's own "Residual" admits labels stay "lightly technical."
- **Rationale:** FR-AUD-4 says audience changes "*only wording*" and §5's Gap-3 decision classes item `detail` as data (hidden when a mockup shows it) but item *labels* (`X create/edit form`) as data too — yet FR-AUD-C1 bans exactly this register ("no *entity, CRUD, ... endpoint*"; "the forms they fill in"). A non-technical reader still meets "create/edit form" jargon on every item. The line is drawn by *field* (title/band vs label/detail) when it should be drawn by *reader-facing surface*.
- **Assumptions / conditions:** Item labels are rendered in the end_user HTML (not only in a hidden/expandable region).
- **Suggested improvements:** See R1-F2 (make the boundary a testable rule keyed on reader-visibility, and give item labels an audience `title`-style override).

**Ask 3 — Per-field degrade leak: is skipping `why` the right fix, or should an authored variant resolve at record level?**
- **Summary answer:** Skipping `why` is a **point patch, not the fix**; specify record-level (or explicit-null) resolution for authored variants.
- **Rationale:** Grounded in `describe.py::_variant` — `pick()` iterates `(fluency_v, role_v, rec)` per field, so *any* field an `end_user` variant omits inherits the architect base verbatim. `why` was the known leak, but `do`/`next`/`what` have the identical exposure; the doc only closes one hole. This is a Context-Correctness-by-Construction gap: a "sparse cell" silently borrows architect voice rather than signaling absence.
- **Assumptions / conditions:** `_variant`'s per-field fallback (lines 78–83) is the shipped resolver; the render-side `why` skip lives in the template/compose, not the resolver.
- **Suggested improvements:** See R1-F3 (spec the authored-variant resolution rule + a jargon-leak assertion over the rendered end_user fields).

**Ask 4 — Sparse-coverage UX risk: what is the completeness bar before a real user, and does unevenness confuse?**
- **Summary answer:** **Depends** — uneven *fluency* depth is low-risk, but uneven *role* completeness needs a stated bar; today there is none.
- **Rationale:** §5 "Residual" says fluency is authored on only 3 spots and future roles are empty. The sparse invariant makes this *safe* (no errors) but not *non-confusing*: a page where 3 spots deepen at `beginner` and the rest stay `intermediate` can read as inconsistent authorial attention. NR-1 permits partial authoring but no requirement defines "ready for a real end_user."
- **Assumptions / conditions:** The v0.4 release target is the `end_user` role specifically (per §5), not multi-role.
- **Suggested improvements:** See R1-F4 (define an `end_user`-role completeness bar as an acceptance gate; scope fluency-unevenness explicitly as accepted).

**Ask 5 — Acceptance test for the omission-catching thesis (falsifiable, short of a user study)?**
- **Summary answer:** **Yes, and it is currently missing** — "renders" is tested (§5: 148 pass) but "*catches* omissions" has no criterion.
- **Rationale:** The entire product differentiator (§1, FR-AUD-C3) is untested; §5 only asserts rendering + byte-identity. A falsifiable proxy exists without a user study: seed-a-gap → assert-the-preview-names-it.
- **Assumptions / conditions:** A fixture plan can be constructed with a deliberately absent field/unwritten section.
- **Suggested improvements:** See R1-F5 (mutation-style acceptance criterion under FR-AUD-C3).

**Ask 6 — `plain_*` derivation robustness across edge-case plans?**
- **Summary answer:** **Mostly robust but under-specified** — `_plain_content` guards `total == 0`, but `_plain_shape`/`_plain_status` have no authored empty-project criterion and pluralization is only informally covered.
- **Rationale:** Grounded in `compose.py`: `_plain_content` handles divide-by-zero (`if overall.total == 0: return "No text to write yet."`) and `_plain` handles singular/plural; but `_plain_shape` on a 0-entity/0-page plan emits "0 things tracked · 0 screens · …" (technically correct, arguably confusing as a *first-time* introduction, FR-AUD-C4), and `_plain_status` returns the reassuring "Everything's planned — nothing missing" even for an *empty* project (all counts zero ⇒ no issues ⇒ false "all good"). No requirement pins these edge outputs.
- **Assumptions / conditions:** Shipped `compose.py` lines 93–125 are the derivation surface; `content_coverage.overall.total` is the only guarded zero.
- **Suggested improvements:** See R1-F6 (edge-case acceptance table for `plain_*`, incl. the empty-project false-positive).

##### Executive summary (≤10 bullets)

- Biggest lever (thesis-critical): NEED is authored-only while the plan already computes the gap signals — omissions can be silently under-reported (R1-F1).
- The omission-catching thesis has **no falsifiable acceptance criterion**; only "renders" and "byte-identical" are tested (R1-F5).
- The per-field degrade leak is closed only for `why`; `what`/`do`/`next` share the identical architect-inheritance path (R1-F3).
- FR-AUD-4's data/presentation line leaves item *labels* ("create/edit form") in jargon that FR-AUD-C1 explicitly bans (R1-F2).
- No stated **completeness bar** for the `end_user` role before it reaches a real user (R1-F4).
- `plain_status` reports "nothing missing" for an *empty* project — a false reassurance for a first-time author (R1-F6).
- FR-AUD-C1's jargon ban is a prose bar with no automated check despite being deterministic and testable (R1-F7).
- OQ-AUD-3's resolution is deferred but §5 already ships the data that would resolve it — the OQ and the build state have drifted (R1-F1 / R1-F8).
- "Byte-identical" (FR-AUD-2) is asserted but the *anchor* it must stay identical to is not pinned (R1-F9).

##### Numbered suggestions

- **R1-F1** *(Validation / Data)* — **Specify NEED as a computed floor the author augments, not authored-only.** FR-AUD-C2 defines NEED as "the author's to-do" (authored), yet §5 ships `_plain_status`/`_plain_content` which already derive unconfirmed/unwritten counts from the plan. Add a clause to FR-AUD-C2 (or resolve OQ-AUD-3 in-doc): NEED MUST include, at minimum, the plan-derived gaps (fields in `not_defined`/`placeholder`, sections below 100% content coverage), with authored prose layered on top. *Anchor:* FR-AUD-C2 "NEED — what *you* must provide … (NEED is the author's to-do)". *Testable:* fixture plan with N `not_defined` fields ⇒ assert NEED enumerates ≥ N items.
- **R1-F2** *(Interfaces / Data)* — **Redraw the FR-AUD-4 boundary on reader-visibility and give item labels an audience override.** §5 classes item labels ("`X create/edit form`") as "data" that stays, but §5 Residual concedes they are "lightly technical" and FR-AUD-C1 bans "form/endpoint" register. Make FR-AUD-4 testable: *any string rendered in the end_user HTML* is subject to FR-AUD-C1; give item labels a `title`-style audience override (as titles already have). *Anchor:* FR-AUD-4 "audience is presentation, not content" + §5 "item labels … are lightly technical". *Testable:* grep the rendered end_user DOM for the FR-AUD-C1 banned-word list ⇒ zero hits (see R1-F7).
- **R1-F3** *(Risks / Data)* — **Spec authored-variant resolution to eliminate the per-field architect leak generally.** `describe.py::_variant.pick()` falls back per field to the architect base for `what`/`why`/`do`/`next`; the doc only patches `why` (skipped in render). Add a requirement: when a `(role,·)` variant is authored, an omitted narration field MUST resolve to empty/absent (record-level or explicit-null), NOT silently to the architect base — OR the doc must state that inheriting base is intended and enumerate which fields are safe. *Anchor:* §5 "`why` is skipped in the end_user render (its base value is architect voice)". *Testable:* author an `end_user` variant omitting `do`; assert rendered `do` is not the architect string.
- **R1-F4** *(Validation)* — **Define an `end_user`-role completeness bar as an acceptance gate.** §5 Residual: fluency on 3 spots, future roles empty — but no requirement states what "done enough for a real user" means. Add a criterion to §5 or a new FR-AUD-C6: the `end_user` role is user-ready when all 10 sections + summary carry authored DOES/WON'T/NEED (fluency remains explicitly optional/sparse). *Anchor:* §5 "Residual (next)". *Testable:* assert every section key has an `end_user` `what`/`wont`/`need` authored.
- **R1-F5** *(Validation)* — **Add a falsifiable omission-catching acceptance criterion under FR-AUD-C3.** The thesis (§1) is untested. Add: given a fixture plan mutated to drop a known field (e.g. remove `phone` from a contact entity) or leave a content section unwritten, the composed end_user view MUST contain a NEED/omission string naming that gap; removing the gap removes the string. *Anchor:* FR-AUD-C3 "the author notices 'where's the phone number?' *here*, not after the build." *Testable:* mutation test (seed-gap ⇒ assert-named; no-gap ⇒ assert-absent).
- **R1-F6** *(Risks / Validation)* — **Pin `plain_*` edge-case outputs, especially the empty-project false reassurance.** `_plain_status` returns "Everything's planned — nothing missing or broken." when all counts are zero — including an *empty* project, contradicting FR-AUD-C4's first-time-viewer framing. Add an acceptance table under §5 or FR-AUD-C5 covering: 0 entities, all `not_defined`, empty project, singular vs plural, `content total == 0`. *Anchor:* `compose.py` `_plain_status` / FR-AUD-C4. *Testable:* parametrized test over the edge table with asserted strings.

##### Stress-test / adversarial pass

- **R1-F7** *(Validation / Security-of-voice)* — **Make FR-AUD-C1's jargon ban an automated deterministic check, not a prose aspiration.** FR-AUD-C1 enumerates a concrete banned-word list ("entity, CRUD, schema, prisma, AI pass, manifest, cascade, FastAPI, endpoint, foreign key") — this is machine-checkable. Add: a test asserts the rendered `end_user` HTML/view-model contains none of the FR-AUD-C1 banned tokens (case-insensitive, word-boundary). *Anchor:* FR-AUD-C1 banned list. *Testable:* the check itself is the acceptance criterion; it also enforces R1-F2.
- **R1-F8** *(Consistency)* — **Reconcile OQ-AUD-3 (open) with §5 (shipped signals).** OQ-AUD-3 asks whether NEED is "derivable from the plan … Investigate next pass," but §5 already ships `_plain_content`/`_plain_status` deriving exactly those figures — the open question and the build status have drifted. Either close OQ-AUD-3 citing §5, or state precisely what remains open (per-*section* vs summary-band derivation). *Anchor:* OQ-AUD-3 "Investigate next pass" vs §5 "OQ-AUD-2 resolved" (OQ-AUD-3 conspicuously left open). *Testable:* doc-consistency check (no OQ contradicts a §5 shipped claim).
- **R1-F9** *(Validation)* — **Pin the byte-identity anchor FR-AUD-2 must hold against.** FR-AUD-2/NR-3 promise "byte-identical" terminal output but name no stored baseline. Add: the acceptance check is a golden-file / snapshot of `--describe` default output that CI diffs on every FR-AUD change. *Anchor:* FR-AUD-2 "byte-identical terminal output"; §5 "terminal `--describe` byte-identical". *Testable:* committed golden file + diff assertion (states *how* "byte-identical" is verified, currently only asserted).

##### Endorsements & Disagreements

- No prior untriaged rounds exist in Appendix C (this is R1). None to endorse or dispute.

#### Review Round R2 — claude-opus-4-8[1m] — 2026-07-18

- **Reviewer**: claude-opus-4-8[1m]
- **Date**: 2026-07-18 20:23:31 UTC
- **Scope**: Single-document requirements review (FR-AUD v0.5), fresh R2 lens. Honors the SETTLED list (role×fluency axis, single-role fluency, authored no-LLM, byte-identical default, reuse-not-overload concierge, sparse-degrading) **and the R1 resolutions** (computed NEED floor R1-F1; authored-variant self-containment R1-F3; jargon ban via `has_jargon` + technical-item hiding R1-F7; real record names kept per R1-F2 Appendix B). Weighted to the 5 R2 focus areas: process-meta leakage → user-benefit framing; the unmodeled-wants blind spot in the omission thesis; information architecture / cognitive load / progressive disclosure; accessibility + internationalization; persona/benefit-framing of the doc itself. No prose rewrites; no triage. Grounded: `descriptive.yaml:197/200/204` (intro strings), `describe.py::_variant`, `render.py` (Rich/markdown surface has no a11y/i18n hooks).

##### Focus-ask answers (address before F-suggestions)

**R2 Ask 1 — Should the spec REQUIRE the end_user surface be couched in user-benefit + actionable terms and forbid process-meta (absolute paths, build-pipeline framing, "we're about to build")?**
- **Summary answer:** **Yes** — and it is currently a gap: FR-AUD-C1 bans *jargon* but not *process/tool-meta*, which is a distinct leak category the doc does not name.
- **Rationale:** FR-AUD-C1 forbids implementation *vocabulary* (entity/CRUD/endpoint…) but says nothing about *process-meta* — the absolute filesystem path (`/Users/…/strtd8/strtd8`) rendered as a subtitle, and the tool-centric intro authored in `descriptive.yaml:197` ("a preview of the app we're about to build for you — before anyone writes a single line of code"). None of those tokens are on the FR-AUD-C1 banned list, so the enforced check (R1-F7) passes them, yet they narrate the *tool's* pipeline, not the *user's* app — the exact register FR-AUD-C4's persona ("does it match what you pictured?") is meant to displace. The doc's own §1 says the author "should approve *what they're building* without learning any of that," which logically extends past jargon to build-pipeline framing.
- **Assumptions / conditions:** The absolute path is actually rendered as a subtitle on the end_user surface (grounded that the intro strings exist in `descriptive.yaml`; the path-as-subtitle is asserted from the focus file — the FR-WV HTML render surface, not this repo's `render.py`, owns it). The line between *orienting* ("this is a preview to review before we build") and *narrating the tool* ("before anyone writes a single line of code") is where the requirement must draw its boundary.
- **Suggested improvements:** See R2-F1 (add a process-meta ban distinct from the jargon ban, with an enumerated forbidden set: absolute paths, "we're about to build", build-pipeline framing) and R2-F2 (require the intro be framed as *what to do and why*, actionable + benefit-first).

**R2 Ask 2 — Does the doc overclaim "catches omissions"? Should FR-AUD-C3 scope the claim to modeled-but-incomplete gaps and add a prompt for unmodeled wants?**
- **Summary answer:** **Yes, it overclaims** — the computed floor (R1-F1) only surfaces gaps that already have a node (`not_defined`/`placeholder`/`invalid`); a field/entity the author *wanted but never modeled at all* has no node and cannot be surfaced.
- **Rationale:** §1 promises the author catches "missing fields, unwritten content, and 'obvious once I saw it' gaps." R1-F1 grounded NEED in `need_items` = plan-flagged statuses (`not_defined`/`placeholder`/`invalid` are all *statuses of things that exist in the plan*). A want that was never captured produces no flag — the preview "literally cannot show what was never captured." FR-AUD-C3's own example ("where's the phone number?") is precisely an *unmodeled* want, yet the shipped mechanism only catches *modeled-incomplete* ones. This is a scope/claim mismatch, not a code bug — the honest framing is "catches modeled-but-incomplete gaps, and *prompts* for unmodeled ones."
- **Assumptions / conditions:** `need_items` is exclusively plan-status-derived (grounded); there is no free-text "what's missing?" capture path in the current surface.
- **Suggested improvements:** See R2-F3 (scope the FR-AUD-C3 / §1 omission claim to modeled-incomplete gaps explicitly) and R2-F4 (add a standing unmodeled-wants prompt — "Is anything you expected NOT here at all?" — as a required, audience-agnostic element, distinct from the computed floor).

**R2 Ask 3 — Is inverted-pyramid + collapsible sections the right IA for a non-technical first-timer? Any progressive-disclosure requirement missing?**
- **Summary answer:** **Partial** — the IA is reasonable but *unspecified as a requirement*; FR-AUD-C4 mandates a framing intro "before any counts or sections" but no requirement governs cognitive load or progressive disclosure below the fold.
- **Rationale:** FR-AUD-C4 pins only the *top* (intro before counts). Below it, the surface renders all 10 sections + summary + DOES/WON'T/NEED per section with no stated disclosure discipline — potentially a wall of text for a first-timer (the persona §1 names). Nothing requires collapsibility, a default-collapsed detail tier, or a "start here / most-important-first" ordering. The doc has an IA *intent* (FR-AUD-C4's inverted-pyramid top) but no IA *requirement* for the body.
- **Assumptions / conditions:** The FR-WV HTML consumer owns actual layout/collapsibility; FR-AUD can still state a content-ordering / disclosure *contract* the render must honor.
- **Suggested improvements:** See R2-F5 (add a progressive-disclosure / cognitive-load requirement: default-visible = intro + summary band + per-section DOES/NEED; secondary detail deferred/collapsible; specify max primary-surface density).

**R2 Ask 4 — Are a11y and i18n in scope, or explicit non-requirements?**
- **Summary answer:** **Neither, today — they are silently absent**, which is itself the defect; the doc should decide explicitly (in-scope requirement OR named NR).
- **Rationale:** The authored `end_user` strings are English-only and hard-coded in `descriptive.yaml`; `render.py` emits no `lang=`, `aria-*`, or contrast/keyboard affordances (grep-confirmed: no a11y hooks in the wireframe render surface). §3 Non-Requirements enumerates NR-1..NR-5 but neither a11y nor i18n appears — so a reader cannot tell if they were considered-and-deferred or simply overlooked. For a layer whose entire purpose is *reaching a non-technical human*, an unstated a11y posture is a credibility gap.
- **Assumptions / conditions:** The end_user HTML is a human-facing rendered artifact (per FR-WV). i18n = the authored strings are the only localizable surface (data-owned, single-home per §0.1) — which actually makes a future i18n hook cheap (Mottainai: strings already externalized).
- **Suggested improvements:** See R2-F6 (add explicit NR-6 a11y-posture + NR-7 i18n-posture, OR a minimal a11y acceptance bar — semantic structure, `lang`, contrast — if in scope) and R2-F7 (note the single-home authored-strings design already enables i18n at low cost; state whether that's a committed future hook or out of scope).

**R2 Ask 5 — Does the spec frame requirements around the user's goal (approve/curate what's being built) or the tool's mechanism? Any requirement that reads as process-centric where it should be benefit-centric?**
- **Summary answer:** **Mixed** — §1 and FR-AUD-C4 are commendably benefit-framed ("is this the app I pictured?"), but several requirements and the authored intro read tool-/mechanism-first, and the doc has no stated persona-framing discipline for the *authored content itself*.
- **Rationale:** FR-AUD-C4's persona question is exemplary. But the authored intro (`descriptive.yaml:200/204`) leads with pipeline framing ("before anyone writes a single line of code"), and FR-AUD-C1's "Speak the author's domain" is a *vocabulary* rule, not a *stance* rule (benefit-first, actionable, second-person "what to do and why"). There is no requirement asserting the end_user surface must be *goal-framed* (help the author approve/curate) rather than *mechanism-framed* (narrate what the tool does next). R2-F1/F2 close the authored-content side; this ask also flags the absence of a single stated framing principle.
- **Assumptions / conditions:** none.
- **Suggested improvements:** See R2-F2 (a stated benefit-first / actionable framing rule for the end_user voice) and R2-F8 (a one-line "framing principle" in §2b: every end_user string serves the author's goal — *approve, curate, supply* — not the tool's narration of its own steps).

##### Executive summary (≤10 bullets)

- Biggest R2 lever: FR-AUD-C1 bans jargon but **not process/tool-meta** — absolute paths and "we're about to build / single line of code" pass the enforced check yet violate the persona (R2-F1, R2-F2).
- The omission thesis (§1, FR-AUD-C3) **overclaims**: the computed floor only catches *modeled-but-incomplete* gaps; genuinely unmodeled wants have no node and can't be shown (R2-F3, R2-F4).
- No **unmodeled-wants capture** ("is anything you expected NOT here at all?") — the one path that could catch the exact "where's the phone number?" case FR-AUD-C3 cites (R2-F4).
- IA below the fold is **unspecified**: FR-AUD-C4 pins the intro but no progressive-disclosure / cognitive-load requirement governs 10 sections × DOES/WON'T/NEED for a first-timer (R2-F5).
- **a11y and i18n are silently absent** — neither an NR nor a requirement; undecided posture is the defect for a human-reaching layer (R2-F6, R2-F7).
- The single-home authored-strings design (§0.1) already makes future i18n cheap (Mottainai) — worth stating as a committed hook or explicit non-goal (R2-F7).
- No stated **benefit-first framing principle** for the authored end_user voice — FR-AUD-C1 is vocabulary, not stance (R2-F2, R2-F8).
- Cross-cut of two R1 accepteds: R1-F7 (jargon check) + R1-F1 (computed NEED) both pass the process-meta strings — the new leak sits in the seam between the two accepted guards (R2-F1).

##### Numbered suggestions

- **R2-F1** *(Validation / Risks)* — **Add a process-meta ban distinct from FR-AUD-C1's jargon ban.** FR-AUD-C1 enumerates implementation *vocabulary* but not *tool/process-meta*: absolute filesystem paths (`/Users/…`), build-pipeline framing, and "we're about to build / before anyone writes a single line of code" (authored at `descriptive.yaml:197/200/204`) all pass the R1-F7 enforced check yet narrate the tool, not the app. Add a clause (new FR-AUD-C1b or extend C1): the `end_user` surface MUST NOT render process-meta — absolute/relative filesystem paths, internal identifiers, or build-pipeline narration. *Anchor:* FR-AUD-C1 banned list (add a second enumerated set); §1 "approve *what they're building* without learning any of that." *Testable:* extend the R1-F7 banned-token check with a path regex (`/[A-Za-z0-9_./-]+/`) and the process-meta phrase set ⇒ zero hits on the rendered end_user surface.
- **R2-F2** *(Validation)* — **Require the end_user voice to be benefit-first and actionable — what to do and why — not tool-narration.** FR-AUD-C1 governs vocabulary and FR-AUD-C4 governs only the top intro; no requirement states the *stance*. Add to FR-AUD-C2 or a new clause: every `end_user` string is framed around the author's goal (approve / curate / supply) and, where it asks for action (NEED), states *why they're doing it*. *Anchor:* FR-AUD-C4 "does it match what you pictured? What's missing?"; the tool-centric intro at `descriptive.yaml:200`. *Testable:* review checklist item + assert the intro string contains no build-pipeline clause (pairs with R2-F1); manual rubric for benefit-framing per section.
- **R2-F3** *(Consistency / Validation)* — **Scope the "catches omissions" claim to modeled-but-incomplete gaps.** §1 and FR-AUD-C3 imply the preview catches *any* missing thing, but the shipped computed floor (R1-F1, `need_items` = `not_defined`/`placeholder`/`invalid`) only surfaces gaps that already have a plan node. Reword §1/FR-AUD-C3 to state the mechanism catches *modeled-but-incomplete* gaps automatically, and *prompts for* unmodeled ones. *Anchor:* §1 "authors discover missing fields … only after the build"; FR-AUD-C3 "the author notices 'where's the phone number?'"; R1-F1 (Appendix A) `need_items` derivation. *Testable:* doc-consistency check — no §1/FR-AUD-C3 claim asserts detection of gaps with no plan node.
- **R2-F4** *(Data / Validation)* — **Add a required unmodeled-wants prompt.** The computed floor cannot surface a want that was never captured (no node ⇒ no flag); FR-AUD-C3's own "where's the phone number?" example is exactly this case. Add a requirement (FR-AUD-C3 extension or new FR-AUD-C6): the end_user surface MUST carry a standing, audience-agnostic prompt inviting the author to name anything expected-but-absent (e.g. "Is anything you expected NOT here at all?"), distinct from and in addition to the computed NEED floor. *Anchor:* FR-AUD-C3 "make 'obvious once seen' gaps explicit"; R2 Ask 2. *Testable:* assert the composed end_user view always contains the unmodeled-wants prompt string, independent of plan gap count (including a fully-planned project — where the computed floor is empty but the prompt still appears).
- **R2-F5** *(Architecture / Validation)* — **Add a progressive-disclosure / cognitive-load requirement for the body.** FR-AUD-C4 pins only the intro ("before any counts or sections"); nothing governs the 10 sections × DOES/WON'T/NEED below it for a first-time non-technical reader (the §1 persona). Add a requirement: primary surface = intro + summary band + per-section DOES + NEED; secondary detail (WON'T rationale, item lists) is deferred/collapsible or clearly subordinate; state a max primary density (e.g. most-important-first ordering). *Anchor:* FR-AUD-C4 "An introduction, not a report"; §1 non-technical persona. *Testable:* content-ordering assertion on the composed view (intro precedes summary precedes sections) + a stated disclosure tier per element; render-side collapsibility owned by FR-WV, cited not restated.
- **R2-F6** *(Ops / Risks)* — **Decide the a11y posture explicitly — NR or minimal acceptance bar.** For a layer whose purpose is reaching a non-technical human, the render surface has no stated semantics/`lang`/contrast/keyboard posture (grep-confirmed: no a11y hooks in `render.py`; the FR-WV HTML owns the DOM). §3 lists NR-1..NR-5 but not a11y. Either add **NR-6 (a11y out of scope, deferred)** with rationale, or a minimal in-scope bar (semantic structure, `lang` attribute, WCAG-AA contrast on the plain band). *Anchor:* §3 Non-Requirements; §1 non-technical persona. *Testable:* if in scope — an axe/contrast check on the rendered end_user HTML; if NR — the doc explicitly names a11y as deferred.
- **R2-F7** *(Data / Ops)* — **State the i18n posture; note the single-home strings already enable it cheaply.** The authored `end_user` strings are English-only, hard-coded in `descriptive.yaml`, but §0.1's "single-source vocabulary ownership" (strings in one home, renderer holds none) means i18n is a low-cost future hook (Mottainai — the externalization cost is already paid). Add **NR-7 (i18n deferred)** or a committed future-hook note; either way state it so the English-only assumption is a *decision*, not an oversight. *Anchor:* §0.1 "Single-source vocabulary ownership"; FR-AUD-C5 authored strings. *Testable:* doc states i18n posture; if committed, assert strings are addressable by a locale key (not inlined in render logic).
- **R2-F8** *(Architecture / Consistency)* — **Add a one-line benefit-framing principle to §2b.** The doc frames the *problem* around the user's goal (§1) but has no single stated principle that the authored *content* must be goal-framed (approve / curate / supply) rather than mechanism-framed. Add to the §2b preamble: "Every end_user string serves the author's goal — approve, curate, or supply — never a narration of the tool's own steps." This gives R2-F1/F2 a governing principle to anchor to. *Anchor:* §2b preamble "the bar it must clear"; FR-AUD-C4 persona question. *Testable:* review-rubric line; each new authored string maps to one of {approve, curate, supply}.

##### Stress-test / adversarial pass

- **R2-F9** *(Risks)* — **Adversarial on R2-F4: an always-on unmodeled-wants prompt on a genuinely complete project risks a false "you missed something" nudge.** If the prompt "Is anything you expected NOT here?" fires even when the plan is fully modeled and the computed floor is empty, a first-time author may distrust a correct preview (the inverse of R1-F6's empty-project false reassurance). Scope R2-F4: the prompt is framed as an *invitation to confirm completeness* ("Anything missing? If not, you're ready"), not an implication of a defect. *Anchor:* R2-F4; R1-F6 (Appendix A, empty-project fix) as the mirror failure. *Testable:* assert the prompt copy on a zero-gap project reads as confirmation, not warning (string check against the warning register).
- **R2-F10** *(Consistency)* — **Adversarial on R2-F1: the process-meta ban must not collide with FR-AUD-C5's "real names" mandate or R1-F2's Appendix-B rejection.** R1-F2 (rejected half) kept the author's *real record names* (Profile, Company) on the surface; R2-F1 must ban *tool/process* meta (paths, pipeline framing) WITHOUT reclassifying legitimate real-data names or the necessary orienting frame ("this is a preview to review before building"). State the boundary in the FR-AUD-C1b clause: real user-data names and a benefit-framed "preview before build" orientation are permitted; filesystem paths, internal ids, and tool-step narration are not. *Anchor:* FR-AUD-C5 "real names"; Appendix B R1-F2 rationale; R2 Ask 1 "where's the line between orienting the user and narrating the tool." *Testable:* the banned-token check (R2-F1) allowlists user-data names and the orienting intro; asserts on paths + pipeline phrases only.

##### Endorsements & Disagreements

- No untriaged prior rounds remain: all 9 R1 F-suggestions are triaged into Appendix A (R1-F1,F3,F4,F5,F6,F7,F2-rule,F8,F9) or Appendix B (R1-F2 label-rename half). Nothing untriaged to endorse or dispute. R2 builds on the R1 accepteds rather than restating them: R2-F1 extends R1-F7's enforced check to a new leak class (process-meta) that the jargon list does not cover; R2-F3/F4 scope and extend R1-F1's computed floor to the unmodeled-wants case it cannot reach.
