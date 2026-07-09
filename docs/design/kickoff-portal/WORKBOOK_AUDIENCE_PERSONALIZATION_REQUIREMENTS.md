# Workbook × Audience Personalization — Requirements

**Version:** 0.5 (Implemented — Era 1 shipped)
**Date:** 2026-07-08
**Status:** IMPLEMENTED (Era 1, classic schema) — see §0.2 Implementation Insights
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
| `KICKOFF_WORKBOOK_INTRO.md` + `"workbook"` key | `concierge_templates/` + `writes.py` | ✓ (shipped, FR-2/FR-3) |

### 0.2 Implementation Insights (v0.5 — post-build)

> Discovered while implementing (Phase 6). The reflective loop continues into code: one CRP-accepted
> item proved mechanically impossible and was corrected.

- **`compact` (Advanced) cannot differ from `light` without breaking byte-identity** — see the FR-2
  ⚠ note. `writes.py`'s `light` path retains `TL;DR` prose and strips only its marker *lines* (injecting
  a newline), so a `TL;DR` region both leaks into `light` and breaks the single-line byte-identity target.
  The doc ships **`PLAIN`-only**; Advanced degrades to `light`. R1-F8/R1-S5's `compact != light`
  assertion is **dropped**; `expanded != light` is retained as the degrade-guard. A distinct Advanced
  compact is deferred (needs a `writes.py` change; natural to fold into era 2).
- **Everything else shipped as specced** — Slice A (tiered Beginner intro), Slice B (🛡️ badge + honest
  gap counts, sort-after-`ok`, fail-open join), FR-9 public predicate, the `build_and_maybe_provision`
  resolution guard (own try, degrades not skips), and the byte-identity baseline test (full-spec `==`).
  A canonical template twin (`docs/design/kickoff/templates/KICKOFF_WORKBOOK_INTRO.md`) was required by
  the packaged-template invariant (`test_writes.py::test_packaged_templates_match_canonical`).

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
  - **Param type (R2-F1/R2-S2):** the `audience` value passed to `build_kickoff_portal_spec` MUST be a
    `KickoffAudience` enum instance (i.e. `AudienceResolution.value`), **not** the `AudienceResolution`
    dataclass nor a raw string. The `tier` param MUST be the string from `disclosure_tier(res.value)`. Any
    on-board display of the audience (OQ-3) reads `audience.value` (the token, e.g. `"beginner"`), never
    `str(audience)` (which would render `"KickoffAudience.BEGINNER"`).
- **FR-2 — Author a tiered workbook experience doc.** A new render-only doc
  (`KICKOFF_WORKBOOK_INTRO.md`, shipped) carries the overview intro prose with a `<!-- PLAIN -->`
  (Beginner expanded) region, so `load_experience_doc` produces a genuinely different Beginner intro.
  - **Byte-identity scope (R1-F5/R1-F7):** the byte-identity guarantee applies to the **narrative intro
    region only** — the substring that moves into the doc. The confirmation-legend table, the dynamic
    status line, and the trailing italic remain **code-appended verbatim** (they are state, not prose;
    the status line is inherently dynamic and cannot be byte-pinned). It is **only** the Intermediate /
    unset (`light`) tier that is byte-identity-guaranteed against today's narrative; Beginner (`expanded`)
    differs (that is the personalization).
  - **⚠ IMPLEMENTATION DISCOVERY (§0.2) — `compact` degrades to `light` by design.** The original R1-F8
    ask (require BOTH `PLAIN` **and** `TL;DR`; assert `compact != light` AND `expanded != light`) proved
    **mechanically impossible** given `writes.py`: the `light` render **retains** `TL;DR` prose (it is an
    excerpt) and **strips its marker *lines***, injecting a newline at the seam. So any `TL;DR` region
    both (a) leaks into `light` and (b) breaks the single-line byte-identity. Since byte-identity is
    load-bearing, the doc ships **`PLAIN`-only**; **Advanced (`compact`) degrades to `light`** (==
    Intermediate). Beginner-expanded is the 90% value; a distinct Advanced compact would require a
    `writes.py` enhancement (deferred, revisited in era 2). The marker-presence gate is therefore
    **`expanded != light`** (proves `PLAIN` slices; guards the silent degrade-to-`light` no-op).
- **FR-3 — Register the workbook doc key.** The new doc MUST be registered in `_EXPERIENCE_DOCS` under a
  stable key (e.g. `"workbook"`) so `load_experience_doc("workbook", tier=…)` resolves it.
- **FR-4 — Render the intro at the resolved tier.** `_overview_panels` MUST render the intro from
  `load_experience_doc("workbook", tier=<resolved>)` instead of the inline string. The dynamic status
  line (`N/total confirmed · …`) and the confirmation-legend table remain appended (they are state, not
  prose) — Slice A tiers **only** the narrative intro region.

**Slice B — audience-default badge (surface knob)**

- **FR-5 — Audience-default override state.** For a field whose `value_path` has an `audience-default:*`
  provenance in `confirmed.yaml`, the Workbook MUST render a distinct state — **"safe default set for
  you"** with a glyph (exact glyph in plan; candidate 🛡️) that **overrides** its extraction-derived
  attention glyph for that row only. This is an override layer, not a new value in the extraction
  `attention` enum.
  - **Glyph distinctness (R1-F1/R1-S1):** the glyph MUST NOT be `✅`, which the intro legend and
    `_ATTENTION_DISPLAY["ok"]` already bind to human/extraction confirmation. Reusing `✅` would make a
    machine-shielded default indistinguishable from a field the user authored — defeating the surface
    knob's honesty goal. Acceptance test: rendered audience-default glyph ≠ `_ATTENTION_DISPLAY["ok"][0]`.
- **FR-6 — Fail-open join.** The provenance join MUST use `load_ledger(project_root)` (tolerant: absent
  or malformed ledger → `{}`). With no audience-default entries, the board MUST be **byte-identical** to
  today (no badges, no schema change to the spec output).
  - **Optional provenance key (R1-F2/R2-F5):** `load_ledger` returns `{value_path: entry}` where `entry`
    is `{value, at, mode[, provenance]}` — `provenance` is an **additive, optional** entry field
    (`confirmation.py:41`). The join reads it via the public predicate `is_audience_default(entry)`
    (FR-9); an entry lacking `provenance` is a legitimate non-shielded entry, **not** an error (no
    KeyError). Note the two-level naming: the outer map key is `value_path`; the inner optional field is
    also called `provenance` — the predicate takes the **entry dict**, not the inner field.
  - **FR-6a — Join asymmetry (R1-F6):** a `value_path` present in the ledger but absent from
    `state.fields` MUST be ignored (no phantom row); a `value_path` in `state.fields` but absent from the
    ledger renders on extraction basis (no badge). Neither may raise. A non-dict/malformed entry
    (`{vp: "oops"}`) yields no badge and the extraction glyph, never a crash.
  - **Testable baseline (R2-F2):** the "byte-identical to today" guarantee presumes a captured pre-change
    baseline; since none exists in the suite today, one MUST be created (mechanism in plan §3 / Step 2).
- **FR-7 — Honest overview counts.** The overview **"Open Gaps (author action)" stat** (`vector({blocked})`)
  and the **`**{blocked} gaps**` figure in the intro status line** MUST NOT count audience-default-shielded
  fields as gaps. The **`Fields Confirmed` gauge and the per-domain `slug · confirmed` ratios are
  explicitly out of scope** (they stay on extraction basis — a shielded field is neither a gap nor a human
  confirmation, NR-6). This resolves OQ-2.
  - **Non-underflow invariant (R1-F3/R2-F4):** the shielded-gap discount MUST NOT produce a gap count
    below zero for any board — including the boundary where **every** blocked field is shielded, which
    MUST display `0` (not a negative number). The discount is over the intersection `blocked ∧ shielded`
    keyed by `value_path` (mechanism in plan Step 5); the invariant lives here.
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
  - **Stale-shield limitation (R2-F3/R2-S6):** the M3 pre-pass (`apply_audience_defaults`) writes
    `audience-default:*` entries at **walk-start**, not at `portal` generation. If a user changes
    `audience:` in `build-preferences.yaml` **without re-running `kickoff walk`**, the prior audience's
    shielded entries remain in `confirmed.yaml`. The next `kickoff portal` will render the **new** tier's
    intro but may still badge fields shielded by the **prior** audience. This is an accepted era-1
    limitation; clearing stale shields requires re-running `kickoff walk` or `kickoff confirm` on those
    fields. (NR-2 holds — this feature does not rewrite the ledger.)

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

_All four opened at v0.2 are now **RESOLVED** by the CRP round (R1/R2). Retained for the audit trail._

- **OQ-1 — Badge glyph/label → RESOLVED.** Glyph is **🛡️** (locked in plan Step 4), label "safe default
  set for you", **distinct from `✅`** (FR-5). Sort rank places audience-default rows **with/after `ok`
  (`_ATTENTION_SORT` rank ≥ 3)** — never at `blocked`'s rank 0 — so a shielded field never re-sorts to the
  "gaps first" ordering it was meant to remove (R1-S2).
- **OQ-2 — Gap recount scope → RESOLVED.** Recount the **two gap-facing widgets only** (intro status line
  + "Open Gaps" stat); the `Fields Confirmed` gauge and per-domain `slug · confirmed` ratios stay on
  extraction basis. Promoted into FR-7 above.
- **OQ-3 — Audience token on the board → RESOLVED: yes.** Render a one-line "Rendered for: {audience}"
  note (reads `audience.value`, FR-1). The append MUST be **structurally gated** on a non-default audience
  (no append at all for Intermediate) — an appended-then-blanked string would perturb the Intermediate
  byte-identity golden (R1-S8).
- **OQ-4 — Intro doc content authority → RESOLVED: single-source.** The workbook doc **owns** the
  narrative intro prose; `portal_spec` renders from it and never restates it. The dynamic status line +
  legend stay code-side (state, not prose). The concatenation seam MUST preserve today's whitespace
  exactly (R2-F6 — verified by the composed-panel golden, plan Step 3).

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

*v0.4 — Post-CRP triage (R1 opus-4.8 + R2 sonnet-4.6, 14 F-suggestions). All 14 accepted (2 routed to
plan test-mechanism). FR-1 gained a param-type contract; FR-2 scoped byte-identity to the narrative +
mandated a marker-presence gate; FR-5 forbade the `✅` glyph collision; FR-6 named the optional
provenance key + added FR-6a join-asymmetry; FR-7 named the two gap figures + non-underflow/zero-floor
invariant; FR-10 documented the stale-shield era-1 limitation; OQ-1..OQ-4 all resolved. Dispositions in
Appendix A.*

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

> **Areas substantially addressed (R1/R2):** glyph collision (FR-5), provenance-key optionality + join
> asymmetry (FR-6/FR-6a), gap-recount scope + non-underflow (FR-7), byte-identity scoping + marker gate
> (FR-2), audience param type (FR-1), mid-project stale-shield limitation (FR-10), all four OQs. Later
> reviewers: do **not** re-propose these.

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-F1 | FR-5 glyph MUST NOT be `✅` (collides with legend/`_ATTENTION_DISPLAY["ok"]`) | R1 opus-4.8 | Applied → FR-5 glyph-distinctness bullet; glyph 🛡️ locked (plan Step 4) | 2026-07-08 |
| R1-F2 | FR-6 join reads the *optional* `provenance` entry key; absence ≠ error | R1 opus-4.8 | Applied → FR-6 optional-key bullet | 2026-07-08 |
| R1-F3 | FR-7 non-underflow invariant belongs in the requirement | R1 opus-4.8 | Applied → FR-7 non-underflow invariant (merged w/ R2-F4 zero-floor) | 2026-07-08 |
| R1-F4 | FR-7 name the two gap figures; exclude gauge/ratios | R1 opus-4.8 | Applied → FR-7 body; resolves OQ-2 | 2026-07-08 |
| R1-F5 | FR-2 byte-identity target = narrative substring only | R1 opus-4.8 | Applied → FR-2 byte-identity-scope bullet | 2026-07-08 |
| R1-F6 | FR-6 join asymmetry (in-ledger-not-in-state & vice-versa) fail-open | R1 opus-4.8 | Applied → new FR-6a | 2026-07-08 |
| R1-F7 | FR-2 state that only Intermediate/`light` is byte-safe | R1 opus-4.8 | Applied → FR-2 byte-identity-scope bullet | 2026-07-08 |
| R1-F8 | FR-2/3 require a positive marker-presence gate (silent degrade-to-light) | R1 opus-4.8 | Applied → FR-2 marker-presence gate; test in plan §3 | 2026-07-08 |
| R2-F1 | FR-1 specify `audience=` type (`KickoffAudience` enum, `.value` for display) | R2 sonnet-4.6 | Applied → FR-1 param-type bullet | 2026-07-08 |
| R2-F2 | FR-6 byte-identity presumes a baseline that must be created | R2 sonnet-4.6 | Applied (intent) → FR-6 testable-baseline bullet; mechanism routed to plan Step 2/§3 | 2026-07-08 |
| R2-F3 | FR-10 mid-project audience change leaves stale shields | R2 sonnet-4.6 | Applied → FR-10 stale-shield limitation | 2026-07-08 |
| R2-F4 | FR-7 zero-floor boundary (all blocked shielded → 0) | R2 sonnet-4.6 | Applied → merged into FR-7 non-underflow invariant | 2026-07-08 |
| R2-F5 | FR-6 clarify the two-level `provenance` naming | R2 sonnet-4.6 | Applied → FR-6 optional-key bullet (entry vs inner field) | 2026-07-08 |
| R2-F6 | FR-2/FR-4 concatenation-seam whitespace must match legacy | R2 sonnet-4.6 | Applied (intent) → OQ-4 resolution; test-mechanism routed to plan Step 3 composed-panel golden | 2026-07-08 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none) | — | — | All R1/R2 requirements suggestions accepted (2 routed to the plan for test mechanism, not rejected). | 2026-07-08 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-07-09

- **Reviewer**: claude-opus-4-8-1m (Claude Opus 4.8, 1M context)
- **Date**: 2026-07-09 01:28:43 UTC
- **Scope**: Requirements-quality review (F-prefix). Grounded in `concierge/confirmation.py`, `concierge/audience.py`, `concierge/writes.py`, `kickoff_experience/portal_spec.py`, `state.py`. Weighted per sponsor focus: (a) extraction↔ledger provenance seam (FR-5/6/7), (b) byte-identity (FR-2/FR-4/FR-6, persona FR-4 / NR-3), (c) Slice A tiered-doc authoring dependency (FR-2/3/4).

**Executive summary (top risks / gaps):**

- **Glyph collision is a live inconsistency, not just an OQ:** FR-5's proposed label **"✅ safe default set for you"** reuses `✅`, which the shipped intro legend (`portal_spec._overview_panels`) already binds to "extracted from your authoring docs" and `_ATTENTION_DISPLAY["ok"]` binds to "confirmed". A viewer cannot distinguish a human-confirmed field from a machine-shielded one. Plan Step 4 leans `🛡️` — FR-5 requirements text must be reconciled or it mandates the ambiguous glyph.
- **Join-key provenance lookup depends on an *optional 4th key* the FR text doesn't name:** `load_ledger` returns `{value_path: {value, at, mode}}`; `provenance` is an *additive, optional* entry field (`confirmation.py:41`). FR-6 should state the join reads `entry.get("provenance")` and tolerates its absence — a missing key must degrade, not throw.
- **FR-7's recount rule is delegated entirely to the plan with no invariant in the requirement itself** — the "must not underflow / can't go negative" property belongs as an acceptance criterion in FR-7, independent of the plan's chosen algorithm.
- **The gap count FR-7 must correct comes from `state.attention_counts` (`blocked`), computed in `state.py`, not from the ledger** — FR-7 should name the exact figures (`_overview_panels` `blocked` stat + intro status line) so the recount can't silently miss one.
- **FR-2 byte-identity is asserted against "today's intro prose" but the shipped `intro` string bundles a legend table + a dynamic status line + a trailing italic** — the requirement must name *which* substring is the byte-identity target (narrative only) vs what stays code-side, or the golden test scope is ambiguous.
- **No acceptance criterion covers "field in ledger but absent from `state.fields`" (or vice-versa)** — the sponsor's join-drift concern. Plan R3 covers it; the requirement should too.
- **Advanced audience (`compact`/TL;DR) is silently outside the byte-identity guarantee** — FR-2 only pins Intermediate=`light`. Correct, but should be stated explicitly so a reader doesn't assume all audiences are byte-safe.

**Numbered suggestions:**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Interfaces | high | In FR-5, replace the "✅ safe default set for you" literal with a glyph explicitly **distinct from `✅`** (defer exact emoji to plan/OQ-1 but forbid `✅`), and add a sentence: "MUST NOT reuse the `✅` glyph, which the intro legend and `_ATTENTION_DISPLAY['ok']` already bind to human/extraction confirmation." | The shipped legend (`portal_spec._overview_panels`) binds `✅ confirmed`="extracted from your authoring docs"; `_ATTENTION_DISPLAY["ok"]=("✅","confirmed")`. Reusing `✅` for a machine-shielded default makes a beginner's auto-defaulted field indistinguishable from a field they authored — defeating the surface knob's honesty goal. | FR-5, first sentence | Test: rendered audience-default row glyph ≠ `_ATTENTION_DISPLAY["ok"][0]` and ≠ the legend's `✅`. |
| R1-F2 | Data | high | In FR-6, state the join reads the **optional** `provenance` entry field via `is_audience_default(entry)` and that a ledger entry lacking `provenance` (the common `{value, at, mode}` shape) is a legitimate non-shielded entry, not an error. | `load_ledger` docstring is `{value_path: {value, at, mode}}`; `provenance` is "additive, optional" (`confirmation.py:41`). FR-6 currently implies every entry is checkable but never says the key is optional — an implementer could assume presence. | FR-6, after "tolerant" clause | Test: ledger entry with no `provenance` key → `is_audience_default` returns False, no KeyError; board byte-identical. |
| R1-F3 | Validation | high | Add an explicit acceptance criterion to FR-7: "the shielded-gap discount MUST NOT produce a gap count below zero for any board, including one where every blocked field is shielded." Keep the algorithm in the plan but pin the invariant in the requirement. | FR-7 delegates the "exact recount rule" wholly to the plan, so the non-underflow guarantee (the sponsor's core concern) has no home in the normative requirement. Invariants belong in the requirement, mechanism in the plan. | FR-7, new final bullet | Test: board with 3 blocked, all 3 shielded → gap stat == 0 (not negative). |
| R1-F4 | Data | high | FR-7 should name the **two concrete figures** it corrects — the `_overview_panels` "Open Gaps (author action)" stat (`vector({blocked})`) and the `**{blocked} gaps**` token in the intro status line — and state that the `Fields Confirmed` gauge and per-domain `slug · confirmed` ratios are **explicitly out of scope** (they stay on extraction basis, NR-6). | These figures derive from `state.attention_counts` (`ac.get("blocked")`), computed in `state.py`, i.e. extraction basis — not the ledger. Naming them prevents an implementer from also (wrongly) discounting the gauge, and closes OQ-2 as a requirement rather than leaving it a plan lean. | FR-7 body | Test: gauge + per-domain ratios byte-identical with/without shielded fields; only the two named gap figures change. |
| R1-F5 | Validation | medium | FR-2's byte-identity target is ambiguous: the shipped `intro` is narrative prose **plus** a legend table **plus** a `**{ok}/{total} … {blocked} gaps**` dynamic line **plus** a trailing italic. State that byte-identity applies to the **narrative region only** (what moves to `KICKOFF_WORKBOOK_INTRO.md`), and that the legend/status/italic remain code-appended verbatim. | Without this, "byte-identical to today's intro prose" could be read as pinning the whole composed string — but the status line is dynamic (state-dependent) and cannot be byte-pinned. FR-4 already says the status line + legend "remain appended"; FR-2 must scope its byte-identity claim to match. | FR-2, byte-identity sentence | Golden test pins `load_experience_doc("workbook", tier="light")` == the narrative substring only; a second test asserts the composed panel (narrative+legend+status) is unchanged for a fixed state. |
| R1-F6 | Risks | medium | Add an FR (or an FR-6 sub-bullet) covering **join asymmetry**: a `value_path` present in the ledger but absent from `state.fields` MUST be ignored (no phantom row); a `value_path` in `state.fields` but absent from the ledger renders on extraction basis (no badge). Neither may raise. | The sponsor flags join-key drift as a top concern. `FieldState.value_path` (`state.py:142`) and the ledger key are independent sources; schema drift can desync them. Plan R3 addresses it but no requirement mandates the fail-open behavior. | New FR-6a or FR-6 bullet | Test: value_path only-in-ledger → no extra row; only-in-state → extraction glyph, no crash. |
| R1-F7 | Architecture | low | FR-2 should state explicitly that **only Intermediate/unset (`light`) is byte-identity-guaranteed**; Beginner (`expanded`) and Advanced (`compact`) intentionally differ. | `disclosure_tier` maps INTERMEDIATE→`light`, BEGINNER→`expanded`, ADVANCED→`compact` (`audience.py:51-53`). A reader could mistakenly expect all audiences to preserve today's output; making the guarantee's scope explicit prevents a false regression report when Advanced legitimately changes. | FR-2, parenthetical after the byte-identity clause | Doc review; test that Advanced board differs from legacy (proves personalization is live). |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F8 | Security | low | FR-2/FR-3 should require a fail-closed check that the authored `KICKOFF_WORKBOOK_INTRO.md` actually contains parseable `<!-- PLAIN -->` and `<!-- TL;DR -->` regions — otherwise `load_experience_doc` silently **degrades to `light` for all tiers** (writes.py A-FR9b), shipping "zero visible personalization" that no byte-identity test would catch (light is the pass case). | This is the exact failure the §0 planning-insights table warns about ("the mechanical swap alone is a no-op"), yet no FR converts it into a verifiable gate. The degrade is silent by design; only a positive marker-presence assertion surfaces it. | FR-2 or FR-3, new acceptance bullet | Test: assert `load_experience_doc("workbook", tier="expanded") != load_experience_doc("workbook", tier="light")` AND `compact != light` — proves markers slice, not just that light renders. |

#### Review Round R2 — claude-sonnet-4-6 — 2026-07-09

- **Reviewer**: claude-sonnet-4-6
- **Date**: 2026-07-09 UTC
- **Scope**: Requirements-quality review (F-prefix). Lens: (a) ops/lifecycle — what happens when audience changes mid-project, stale shielded entries, re-generation semantics; (b) test-strategy completeness — are byte-identity and fail-open guarantees testable as written; (c) interface/data contracts — `audience=` type, `provenance` shape, internal call-site implications. Does NOT re-propose R1 items.

**Executive summary (top risks / gaps):**

- **FR-1 lacks an `audience=` type contract**: the requirement says "pass the resolved tier (and audience token) into `build_kickoff_portal_spec` as parameters" but does not specify whether `audience` is a `KickoffAudience` enum, a string token (`"beginner"`), or an `AudienceResolution` dataclass. The plan inherits this ambiguity and OQ-3's display requirement depends on it.
- **FR-6's byte-identity acceptance criterion is untestable as written**: "byte-identical to today" requires a pre-change golden, but no such golden exists in the test suite (confirmed by reading `test_kickoff_portal_spec.py`). The requirement needs to specify how the baseline is captured.
- **FR-10 (regen is trigger) is silent on mid-project audience change**: when a user switches `audience:` in `build-preferences.yaml`, the `audience-default:*` entries written by the prior walk remain in `confirmed.yaml`. The badge re-renders on the new audience's tier, but stale shields from the old pre-pass may still appear. FR-10 should state this is a known era-1 limitation.
- **FR-7's acceptance criterion doesn't cover the case where all blocked fields are shielded (gap stat = 0)**: the requirement says MUST NOT count shielded fields as gaps but does not explicitly require the stat to reach zero and stay there — the non-negative floor is in the plan but not in the requirement.

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | Interfaces | high | In **FR-1**, add a sub-bullet specifying the **type of the `audience` param**: "the `audience` value passed to `build_kickoff_portal_spec` MUST be a `KickoffAudience` enum instance (from `AudienceResolution.value`), not the `AudienceResolution` dataclass, not a raw string token. The tier param MUST be the string from `disclosure_tier(res.value)`." | FR-1 says "pass the resolved tier (and audience token)" but `resolve_audience_preference` returns an `AudienceResolution` dataclass. Three valid extraction choices exist; `disclosure_tier` coerces any of them silently. The type must be stated so OQ-3's "Rendered for: {audience}" display knows to call `.value` for the string. Without it, `str(KickoffAudience.BEGINNER)` → `"KickoffAudience.BEGINNER"` (wrong). | FR-1, new sub-bullet after "pass the resolved tier" | Test: `build_kickoff_portal_spec(..., audience=KickoffAudience.BEGINNER)` → OQ-3 note contains `"beginner"`, not `"KickoffAudience.BEGINNER"`. |
| R2-F2 | Validation | high | In **FR-6**, add an explicit acceptance criterion for the byte-identity guarantee: "The baseline MUST be captured as a pre-change golden fixture (a snapshot of `build_kickoff_portal_spec(demo_state, "demo")` with all default params before any code change), stored in the test suite and asserted byte-for-byte post-change." Rationale: "byte-identical to today" is vacuously satisfied if no baseline exists. | Reading `test_kickoff_portal_spec.py`: there is no snapshot/golden test — only structural assertions (uid shape, tag list, panel types). The "existing snapshot" the plan references does not exist. Without a concrete pre-change capture, the byte-identity requirement is untestable. The requirement should mandate the baseline creation as part of the FR-6 acceptance gate. | FR-6, after "byte-identical" clause | New test creates and pins the baseline dict before code changes land; post-change `==` assertion fails on any perturbation. |
| R2-F3 | Ops | medium | Add a new sub-bullet to **FR-10**: "An era-1 known limitation: if the user changes `audience:` in `build-preferences.yaml` without re-running `kickoff walk` (the M3 pre-pass), the prior audience's `audience-default:*` entries remain in `confirmed.yaml`. On the next `startd8 kickoff portal`, the board will render the new tier's intro prose but may show badges for fields shielded by the *prior* audience. Clearing stale shields requires re-running `kickoff walk` or manually running `kickoff confirm` on those fields." | `apply_audience_defaults` (the M3 pre-pass, per NR-2) runs at walk-start, not at `portal` generation. Switching audience changes the board's tier (via `disclosure_tier`) but does not rewrite the ledger. The `confirmed.yaml` retains whatever the prior pre-pass wrote. The requirement currently says nothing about this state, which will cause user confusion and bug reports. | FR-10, new limitation sub-bullet | Manual test (not automated): set beginner → walk → set advanced → portal → verify stale beginner shields appear; document as intended era-1 behavior. |
| R2-F4 | Validation | medium | In **FR-7**, add an explicit acceptance criterion for the **zero-floor case**: "When ALL `blocked` fields are audience-default-shielded, the 'Open Gaps' stat and the intro gap count MUST display `0`, not a negative number." R1-F3 pins the non-underflow invariant; this is the boundary case (all blocked are shielded) that tests must cover explicitly to verify the floor is `max(0, blocked - shielded_gaps)`. | FR-7 says "MUST NOT count audience-default-shielded fields as gaps" which implies non-negative but does not mandate the zero-floor explicitly. The boundary test (3 blocked, 3 shielded → 0) is different from the general non-underflow test (3 blocked, 2 shielded → 1); both must be covered. R1-F3 added the invariant; this closes the boundary case. | FR-7, acceptance criterion bullet | Test: `state` with 3 blocked fields all shielded → "Open Gaps" stat = 0, intro status line reads `**0 gaps**`. |
| R2-F5 | Data | low | In **FR-6**, clarify the **shape of `provenance` as it enters `build_kickoff_portal_spec`**: it is `{value_path: raw_entry}` where `raw_entry` is the dict returned by `load_ledger` (shape `{value, at, mode[, provenance]}`). Add: "The provenance-presence field (`entry.get('provenance')`) is the optional key that `is_audience_default` inspects; the map key is `value_path` (the ledger's primary key)." This names the exact two levels of the dict hierarchy so an implementer can't confuse the outer map key with the inner entry field named `provenance`. | The inner entry field and the outer concept are both called "provenance" — `provenance = {value_path: entry}` where `entry` may contain a `"provenance"` key. Two things named `provenance` at two nesting levels is a naming collision risk. `confirmation.py:41` documents this but the requirement should spell it out to prevent a confusing "pass the provenance field, not the entry" bug. | FR-6, after "tolerant" clause | Code review: verify `portal_spec` calls `is_audience_default(provenance.get(f.value_path))` (passing the entry dict), not `is_audience_default(provenance.get(f.value_path, {}).get("provenance"))` (passing the inner provenance field). |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F6 | Risks | low | **FR-4 + FR-2 together** have a gap: `_overview_panels` currently appends the dynamic status line as a code-side string after the intro. After Step 3, it calls `load_experience_doc("workbook", tier=tier)` and then appends the status line. If `load_experience_doc` returns a string that already ends with a `\n`, and the appended status line also starts with `\n`, the composed panel has a double blank line that the pre-change panel did not have — and the byte-identity golden fails. The requirement should state: "the concatenation seam between `load_experience_doc` output and the appended status line MUST produce the same whitespace as the current inline string construction." | Looking at `portal_spec.py:149-162`: the current inline string uses `\n\n` to join the legend table and the status line. `load_experience_doc` strips the doc body at the end (`body.strip()`, `writes.py:210`). A naive concatenation (`intro + "\n\n" + status_line`) must match the legacy string's whitespace exactly. If `tier="light"` produces trailing whitespace differently from the current inline, the byte-identity test fails for a non-functional reason. | FR-2, byte-identity acceptance bullet | Test: `load_experience_doc("workbook", tier="light") + "\n\n" + status_line` == the legacy `intro` string exactly (splitting on the status-line boundary). |

**Endorsements** (prior untriaged requirements suggestions this reviewer agrees with):
- R1-F1: Glyph distinctness is blocking — endorsing for immediate triage.
- R1-F3: Non-underflow invariant belongs in the requirement, not the plan — endorsing.
- R1-F8: Positive marker-slice assertion is the only guard against the silent degrade-to-light failure — endorsing for high priority.
