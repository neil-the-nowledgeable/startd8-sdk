# Workbook × Audience Personalization — Requirements

**Version:** 0.3 (Post lessons-learned hardening — ready for CRP)
**Date:** 2026-07-08
**Status:** Draft (reflective-requirements loop; pre-CRP)
**Owner doc it derives from:** `WORKBOOK_AUDIENCE_PERSONALIZATION_NEXT_STEPS.md` (research; §3 slices, §4 eras)
**Scope:** **Era 1 only** — the classic-schema (Grafana < 13.1) port of the kickoff `audience` lens
onto the Digital Project Workbook dashboard. Era 2 (live in-browser switching) is a **non-requirement
here** and folds into `../dynamic-dashboards/` (FR-8/FR-9).

---

## 0. Planning Insights (Self-Reflective Update)

> What changed between v0.1 (the next-steps doc's framing, taken as the pre-planning draft) and v0.2,
> after reading the actual audience + portal code. Planning revealed **4 corrections**; the headline is
> that **Slice A is not the cheap one** and **Slice B is well-supported by existing primitives**.

| v0.1 assumption (from next-steps §3) | Planning discovery | Impact |
|---|---|---|
| Slice A = "swap the hardcoded intro string for the tiered `load_experience_doc`" (Low effort) | `_EXPERIENCE_DOCS` registers **exactly one key** (`"intro"` → `KICKOFF_EXPERIENCE_INTRO.md`). There is **no workbook doc**. Calling `load_experience_doc` on a doc with no `<!-- PLAIN -->`/`<!-- TL;DR -->` markers **degrades to `light` for all tiers** (writes.py A-FR9b) → byte-identical → **zero visible personalization**. | Slice A now **requires authoring a tiered workbook experience doc + registering a `"workbook"` key** (FR-2/FR-3). The mechanical swap alone is a no-op. Effort Low→**Med**; it carries real content work. |
| `build_kickoff_portal_spec` can resolve the audience internally | The spec builder is a **pure, no-I/O function** (docstring: "no I/O"). Audience resolution reads `build-preferences.yaml` + global config — that's I/O. | Resolution must live in the **I/O caller** `portal_build.py` (which already holds `root`) and pass `audience`/`tier` **as parameters** (FR-1). Keeps the purity contract. Pattern already proven at `concierge_view._build_audience_block(project_root)` — reuse it. |
| Slice B "needs a new data join" (correct, but unspecified) | The join is **well-supported**: `load_ledger(project_root)` returns `{value_path: {…, provenance?}}`; `_is_audience_default(entry)` already detects the `audience-default:<slug>` stamp; join key `value_path` is shared with `FieldState`. Ledger read is **tolerant** (absent/malformed → `{}`). | Slice B is **fail-open by construction** (FR-6): no ledger → no badges → byte-identical. Only new asset needed is a **public** audience-default predicate (promote `_is_audience_default`) — FR-9. |
| The badge is "a 4th presentation state" alongside ok/review/blocked/backlog | A shielded field is written to the ledger as a **confirmed value**, but its *extraction* attention is independent (often `blocked`/gap, since a beginner hasn't authored it). The badge must **override** the extraction attention for audience-default fields. | FR-5: the audience-default state is an **override layer** on the field row, not a 5th value in the extraction `attention` enum. It supersedes the extraction glyph for that field only. |

**Resolved open questions (from next-steps §6):**
- **OQ-5 (field granularity) → coarse for v1.** Keep one text panel per domain (today's shape); render the
  audience-default state **inline in the field table row** (a per-row glyph/label swap), not as separate
  panels. Separate-panel-per-field is an era-2 concern (per-field conditional hiding) — NR-4.
- **OQ-6 (disclosure depth) → intro-panel-only for v1.** Slice A tiers **only the overview intro panel**
  via a new workbook experience doc. Per-domain What/Why/Who tiering (`explain_input_domain` gaining a
  `tier=`) is **deferred** — NR-3 (this was next-steps Slice C).
- **Era choice → Era 1 now (this doc).** The rendering logic (tier selection, provenance→badge) is reused
  in era 2; only the *trigger* changes (baked-at-generation → runtime variable). Era 1 is not throwaway.

### 0.1 Lessons-Learned Hardening (v0.3)

> Applied the SDK Design-Docs lessons before CRP. Two changed the draft:

- **[Phantom-reference audit]** — grepped every code symbol this spec names against its owning module.
  Found one phantom: the I/O caller was named `portal_build.build_kickoff_portal`, which **does not
  exist** — the real entry that calls `build_kickoff_portal_spec` is `build_and_maybe_provision`
  (`portal_build.py:244`). Corrected in FR-1 and §5. All other symbols verified present:
  `resolve_audience_preference`, `disclosure_tier`, `load_ledger`, `_is_audience_default`,
  `AUDIENCE_DEFAULT_PREFIX`, `load_experience_doc`, `_EXPERIENCE_DOCS`, `AUDIENCE_PROFILES`,
  `audience_defaults`, `_overview_panels`, `_manifest_section`, `_build_audience_block`,
  `explain_input_domain`. (Reference-audit table below.)
- **[Leg 1 #5 — single-source vocabulary ownership]** — the intro prose currently lives inline in
  `portal_spec` and would be *duplicated* into the new workbook doc, a classic drift seam. Hardened FR-2 +
  OQ-4 to require the workbook experience doc **own** the narrative intro prose (single source); the
  dynamic status line + confirmation-legend stay code-side as *state*, not prose, so nothing is stated in
  two places. `portal_spec` renders from the doc, never restates it.

**Reference audit (symbol → owning module, verified 2026-07-08):**

| Symbol | Module | Exists |
|---|---|---|
| `resolve_audience_preference`, `disclosure_tier`, `AudienceResolution` | `concierge/audience.py` | ✓ |
| `load_ledger`, `_is_audience_default`, `AUDIENCE_DEFAULT_PREFIX`, `audience_default_provenance` | `concierge/confirmation.py` | ✓ |
| `load_experience_doc`, `_EXPERIENCE_DOCS` (1 key: `"intro"`) | `concierge/writes.py` | ✓ |
| `AUDIENCE_PROFILES`, `audience_defaults` | `kickoff_experience/manifest.py` | ✓ |
| `build_kickoff_portal_spec`, `_overview_panels`, `_manifest_section`, `_ATTENTION_DISPLAY` | `kickoff_experience/portal_spec.py` | ✓ |
| `build_and_maybe_provision` (I/O caller) | `kickoff_experience/portal_build.py` | ✓ (was mis-named `build_kickoff_portal`) |
| `_build_audience_block` (reuse pattern) | `kickoff_experience/concierge_view.py` | ✓ |
| `is_audience_default` / `audience_default_slug` (public predicate) | `concierge/confirmation.py` | **to-be-created (FR-9)** |
| `KICKOFF_WORKBOOK_INTRO.md` + `"workbook"` key | `concierge_templates/` + `writes.py` | **to-be-created (FR-2/FR-3)** |

---

## 1. Problem Statement

The kickoff `audience` lens (Beginner / Intermediate / Advanced) already personalizes the CLI, web, and
TUI surfaces — prose density (the **disclosure** knob) and which fields get prompted (the **surface**
knob, via a walk-start pre-pass that writes `audience-default:<slug>` shielded entries). The **Digital
Project Workbook** Grafana dashboard consumes **none** of it: it renders one fixed prose density and
derives every field's attention purely from **extraction status**, blind to the `confirmed.yaml`
provenance ledger. A Beginner whose 3 fields were auto-shielded *for them* still sees a board that
screams "🔴 3 gaps — author action needed."

| Component | Current State | Gap |
|-----------|--------------|-----|
| Overview intro panel (`portal_spec._overview_panels`) | one hardcoded prose string, one density | no audience → no tiered intro |
| Per-field rows (`portal_spec._manifest_section`) | attention from extraction only (ok/review/blocked/backlog) | audience-default-shielded fields render as gaps, not as "safe default set for you" |
| `build_kickoff_portal_spec` | pure fn, no audience param | no channel to receive the resolved audience |
| Workbook experience doc | none exists (only `"intro"`) | nothing tiered to render for Slice A |

## 2. Requirements

**Slice A — tiered overview intro (disclosure knob)**

- **FR-1 — Resolve audience in the I/O caller.** `portal_build.build_and_maybe_provision` (the I/O entry
  that calls `build_kickoff_portal_spec`) MUST resolve the effective audience via
  `resolve_audience_preference(root)` and its `disclosure_tier(...)`, and pass the
  resolved tier (and audience token) into `build_kickoff_portal_spec` as parameters. The spec builder
  stays a pure function (no new I/O inside it).
- **FR-2 — Author a tiered workbook experience doc.** A new render-only doc (e.g.
  `KICKOFF_WORKBOOK_INTRO.md`) MUST carry the overview intro prose with `<!-- PLAIN -->` (Beginner
  expanded) and `<!-- TL;DR -->` (Advanced compact) regions, so `load_experience_doc` produces a
  genuinely different intro per tier. Intermediate (`light`) MUST be **byte-identical** to today's intro
  prose (persona FR-4 byte-identity for the unset/Intermediate user).
- **FR-3 — Register the workbook doc key.** The new doc MUST be registered in `_EXPERIENCE_DOCS` under a
  stable key (e.g. `"workbook"`) so `load_experience_doc("workbook", tier=…)` resolves it.
- **FR-4 — Render the intro at the resolved tier.** `_overview_panels` MUST render the intro from
  `load_experience_doc("workbook", tier=<resolved>)` instead of the inline string. The dynamic status
  line (`N/total confirmed · …`) and the confirmation-legend table remain appended (they are state, not
  prose) — Slice A tiers **only** the narrative intro region.

**Slice B — audience-default badge (surface knob)**

- **FR-5 — Audience-default override state.** For a field whose `value_path` has an `audience-default:*`
  provenance in `confirmed.yaml`, the Workbook MUST render a distinct state — **"✅ safe default set for
  you"** (glyph + label TBD in plan) — that **overrides** its extraction-derived attention glyph for that
  row only. This is an override layer, not a new value in the extraction `attention` enum.
- **FR-6 — Fail-open join.** The provenance join MUST use `load_ledger(project_root)` (tolerant: absent
  or malformed ledger → `{}`). With no audience-default entries, the board MUST be **byte-identical** to
  today (no badges, no schema change to the spec output).
- **FR-7 — Honest overview counts.** The overview "Open Gaps (author action)" stat and the gap count in
  the intro status line MUST NOT count audience-default-shielded fields as gaps. (A shielded field is a
  set default, not an unaddressed gap.) The exact recount rule is specified in the plan; the requirement
  is that a Beginner's headline gap number reflects *their* reduced surface.
- **FR-8 — Transient by design.** When a shielded field is later ratified by `kickoff confirm` (which
  strips the `audience-default` provenance → the entry becomes explicit), the badge MUST disappear and the
  row revert to the normal confirmed state. No extra bookkeeping — this falls out of reading live
  provenance each build.

**Enablers**

- **FR-9 — Public audience-default predicate.** Promote a public helper (e.g.
  `is_audience_default(entry)` or `audience_default_slug(entry)`) from the existing private
  `confirmation._is_audience_default`, so `portal_spec` reads provenance without reaching into a private
  symbol. Single-source the `audience-default:` prefix logic in `confirmation.py`.
- **FR-10 — Regeneration is the era-1 trigger.** Switching audience takes effect on the next
  `startd8 kickoff portal` (re-render + re-provision). The board is baked at the audience resolved at
  generation time. This is the accepted era-1 limitation (live switching is era 2 / NR-1).

## 3. Non-Requirements

- **NR-1 — No live in-browser audience switching.** No runtime `audience` Grafana variable, no conditional
  rendering, no Grafana ≥13.1 dependency. That is Era 2, owned by `../dynamic-dashboards/` (FR-8/FR-9).
- **NR-2 — No change to audience resolution / pre-pass semantics.** This feature only *consumes*
  `resolve_audience_preference`, `disclosure_tier`, `load_experience_doc`, and the ledger provenance. It
  does not touch `apply_audience_defaults`, `AUDIENCE_PROFILES`, or the ladder.
- **NR-3 — No per-domain prose tiering (next-steps Slice C).** `explain_input_domain` does not gain a
  `tier=` parameter in v1. Only the overview intro is tiered.
- **NR-4 — No per-field panel split.** Fields stay in the coarse one-panel-per-domain table (OQ-5 coarse).
- **NR-5 — No writes.** The Workbook remains read-only (Workbook NR-3). The badge is a *view* of existing
  ledger state; this feature never writes `confirmed.yaml` or any input.
- **NR-6 — No new attention value.** The extraction `attention` enum (ok/review/blocked/backlog) is
  unchanged; the audience-default state is a presentation override, not a new extraction class.

## 4. Open Questions

- **OQ-1 — Badge glyph/label.** "✅ safe default set for you" is the intent; the exact emoji + short label
  + sort rank (where audience-default rows sit relative to ok/review/blocked/backlog) is a plan detail.
  Candidate: a dedicated glyph (e.g. 🛡️ or ⭐) so it reads as *distinct from* human-confirmed ✅.
- **OQ-2 — Gap recount scope (FR-7).** Recount only the two overview widgets (intro status line +
  "Open Gaps" stat), or also the per-domain `slug · confirmed` ratios? Leaning: recount the gap-facing
  widgets; leave the confirmed-ratio gauges alone (a shielded field is neither a gap nor a human
  confirmation). Resolve in plan.
- **OQ-3 — Should the audience token surface on the board?** e.g. a small "Rendered for: Beginner" note so
  a viewer knows the board is personalized (and stale if the audience later changes). Low cost, aids the
  era-1 "baked at generation time" transparency. Recommend yes; confirm in plan.
- **OQ-4 — Intro doc content authority.** Does the new `KICKOFF_WORKBOOK_INTRO.md` *move* the intro prose
  out of `portal_spec` (single-source, doc owns it) or *duplicate* it? Single-source (move it) — but the
  dynamic status line stays code-side. Confirm the seam in plan.

## 5. Dependencies / Relates-To

- **Audience feature (owned; cite, don't re-spec):** `concierge/audience.py`
  (`resolve_audience_preference`, `disclosure_tier`), `concierge/confirmation.py` (`load_ledger`,
  `_is_audience_default`, `AUDIENCE_DEFAULT_PREFIX`), `concierge/writes.py` (`load_experience_doc`,
  `_EXPERIENCE_DOCS`), `kickoff_experience/manifest.py` (`AUDIENCE_PROFILES`).
  Persona spec: `docs/design/kickoff/PERSONA_EXPERIENCES_{REQUIREMENTS,PLAN}.md`.
- **Workbook (the surface):** `kickoff_experience/portal_spec.py`
  (`build_kickoff_portal_spec`, `_overview_panels`, `_manifest_section`),
  `kickoff_experience/portal_build.py` (`build_and_maybe_provision`, the I/O caller),
  `WORKBOOK_PROJECT_START_REQUIREMENTS.md` (read-only NR-3).
- **Proven pattern to reuse:** `kickoff_experience/concierge_view._build_audience_block(project_root)` —
  already does `resolve_audience_preference` + `disclosure_tier` for CLI/TUI/web parity.
- **Era-2 successor (do NOT build here):** `docs/design/dynamic-dashboards/` on branch
  `origin/docs/dynamic-dashboards-spec` (`c2ade4fe`) — its FR-8/FR-9 name this exact consumer; gated on
  the v2 emit path + Grafana ≥13.1 upgrade.

---

*v0.2 — Post-planning self-reflective update. Slice A re-scoped (mechanical swap → tiered doc authoring +
key registration), Slice B confirmed well-supported (fail-open ledger join), 3 open questions from
next-steps §6 resolved (era, OQ-5 coarse, OQ-6 intro-only), 4 new plan-detail questions opened. Era 2
excluded as NR-1.*

*v0.3 — Post lessons-learned hardening. Applied 2 SDK Design-Docs lessons: [Phantom-reference audit]
(fixed the `build_kickoff_portal` → `build_and_maybe_provision` phantom; added a reference-audit table)
and [Leg 1 #5 single-source vocabulary ownership] (workbook doc owns the intro prose; `portal_spec`
cites, never restates). Ready for CRP review.*
