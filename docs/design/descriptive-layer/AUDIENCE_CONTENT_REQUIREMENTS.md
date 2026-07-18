# Audience & Content Layer — Requirements (speaking the app to its non-technical author)

**Version:** 0.3.1 (Draft — post-planning + lessons + principle hardening; pre-CRP)
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
- **OQ-B → HTML defaults to `(end_user, beginner)`; terminal to base (architect).** Unset everywhere ⇒
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
  `audience` map providing `what`/`why`/`do`/`next` variants keyed by `role` and, optionally, `fluency`.
  **Sparse + degrading:** resolution is `(role, fluency)` → `(role, ·)` → **base** (the current top-level
  fields = architect/intermediate). An absent cell is never an error. Keyed on the unit's stable key, not
  its label. (Builds FR-DL-1.)
- **FR-AUD-2 — Defaults preserve today.** Unset role/fluency ⇒ base ⇒ **byte-identical** terminal output.
  The wireframe-visual HTML requests `(end_user, beginner)`; the terminal `--describe` stays base (architect).
- **FR-AUD-3 — Resolver mirrors the concierge ladder, distinct axis.** `describe(section, plan, *, role,
  fluency)` resolves per FR-AUD-1; a project/global default MAY be set via the same flag→project→global→default
  precedence `concierge/audience.py` uses — but on `FR-AUD`'s own key, never by overloading `KickoffAudience`.
- **FR-AUD-4 — Audience is orthogonal to data.** Switching audience changes *only wording*; the shape, counts,
  statuses, mockups, and the plan JSON are identical across audiences (audience is presentation, not content).

## 2b. Requirements — the end-user content (what the words must do)

> These define the CONTENT to be authored (the prose lands next pass; here is the bar it must clear).

- **FR-AUD-C1 — Plain language, zero SDK jargon.** The `end_user` voice MUST avoid implementation vocabulary:
  no *entity, CRUD, schema, prisma, AI pass, manifest, cascade, FastAPI, endpoint, foreign key*. Speak the
  author's domain: *the things your app keeps track of, the pages people visit, the forms they fill in, the
  parts the computer fills in for you*.
- **FR-AUD-C2 — The DOES / WON'T / NEED framing.** Each section's end-user narration answers three questions,
  not one: **DOES** — what you're getting; **WON'T** — what this deliberately does *not* include (set
  expectations, prevent silent surprise); **NEED** — what *you* must provide (content to write, fields to
  confirm, decisions to make). (DOES/WON'T map to NODE-SCHEMA `does`/`wont`; NEED is the author's to-do.)
- **FR-AUD-C3 — Surface omissions, don't imply them.** The content MUST make "obvious once seen" gaps
  *explicit*: forms name what they do **not** collect; content sections name what is **unwritten**; empty
  states are called out. The goal: the author notices "where's the phone number?" *here*, not after the build.
- **FR-AUD-C4 — An introduction, not a report.** The top of the HTML frames the review task for a first-time
  viewer: *"Here's the app we're about to build for you — does it match what you pictured? What's missing?"*
  — before any counts or sections.
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

## 4. Open Questions

- **OQ-AUD-1 — Fluency values for reading.** Reuse `beginner/intermediate/advanced` labels, or a reading-specific
  set (`plain/standard/detailed`)? (Lean: reuse the concierge labels to avoid a second vocabulary.)
- **OQ-AUD-2 — Where do project/global audience defaults live** if the HTML default isn't enough — `build-preferences.yaml`
  (concierge's home) or a wireframe-visual flag (`--audience end_user`)? (Lean: a `--audience` flag now; project pref later.)
- **OQ-AUD-3 — NEED as data vs prose.** Is "what you must provide" derivable from the plan (unwritten content %,
  unconfirmed fields) so it's partly *computed*, not only authored? (Investigate next pass; FR-AUD-C3 candidates.)

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
  `compose`/`render_html` thread `role`/`fluency`; default = base (byte-identical); HTML = `(end_user, beginner)`.
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
- **Residual (next):** the `Ready to build?` value + item labels (`X create/edit form`) are lightly
  technical; fluency is authored on 3 spots (extend to more sections on demand — sparse invariant).

---

*v0.4 — Abstraction + end-user content both built (§5). Grounded on the three real audience abstractions.*
*v0.3.1 — Post planning + lessons + principle hardening. Grounded on the three real audience abstractions.
Builds the adopted FR-DL-1 field as a sparse, degrading (role × fluency) axis; reuses the concierge ladder +
byte-identical-default; defines the end-user DOES/WON'T/NEED content bar. Abstraction-first (this pass);
end-user prose authored next pass. Ready for CRP.*
