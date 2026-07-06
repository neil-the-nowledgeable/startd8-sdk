# Kickoff Persona Experiences — Requirements

**Version:** 0.5 (Audience naming resolved; panel findings folded)
**Date:** 2026-07-06
**Status:** Draft
**Owners:** kickoff kernel (`concierge/`, `kickoff_experience/`)
**Related:** `ADR_RETIRE_RED_CARPET_WIZARD.md`, `KICKOFF_UX_v0.5`, value-input-confirmation, content-contract
**Plan:** `PERSONA_EXPERIENCES_PLAN.md`

---

## 0. Planning Insights (Self-Reflective Update)

> This section documents what changed between v0.1 (pre-planning) and v0.2 (post-planning). The
> planning pass touched the real seams and falsified the draft's central persistence assumption plus
> three more — a >30% revision, i.e. the loop working as intended.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| FR-1: persona is "stored the way `posture` is stored." | **`posture` is NOT persisted** — it's a per-invocation flag defaulting to `"prototype"` (`writes.py:168`, `cli_concierge.py:317`, `web.py:962`). The guided "current_mode" reads `deployment.mode` from `app.yaml`, a different field; the flow explicitly never records a posture choice (`concierge_view.py:666`). | FR-1 retargeted: persona mirrors the **`guided` preference ladder** (project `build-preferences.yaml` → global `~/.startd8/config.json` → default), which is the *real* persisted, changeable per-project preference (`guided_routing.py:113`, `build_preferences.py:44`, `config.py:299`). |
| FR-6: extend `FieldDef.provenance_default`. | Two provenance concepts. `FieldDef.provenance_default` is a static template fact in a **closed** set `{authored, estimate, config-default, templated}` (`manifest.py:38`). Per-decision provenance lives in the **ledger** `confirmed.yaml` as `{value, at, mode}`, `mode ∈ {set, as-is}` (`confirmation.py:37`). | `audience-default:<slug>` is a **ledger** provenance, not a `FieldDef` value. FR-6 extends the ledger schema (bump `kickoff.confirmed.v1 → v2`), never the closed `PROVENANCE_DEFAULTS` set. |
| FR-11: the walk can "skip fields while writing them." | The walk **skips by NOT writing** — Enter appends to `skipped[]` and moves on; nothing persists (`confirm_walk.py:141`). "Skip-but-write" is not a walk behavior. | FR-11 retargeted to a **pre-pass** (`apply_audience_defaults`) that writes persona defaults via the existing `build_confirm_plan`/`apply_confirm` *before* the walk; ledgered fields are then auto-dropped by the unchanged `awaiting_fields`. The walk loop is untouched. |
| FR-9: `compact` generalizes to 3 tiers. | `compact` is a **binary** HTML-comment slice (`<!-- TL;DR -->…`, `writes.py:126`). No third region; beginner plain-language prose exists nowhere. | FR-9 is single-source-safe **only** if the expanded tier is authored as **additional delimiter-marked regions inside the same doc** (`<!-- PLAIN -->…`), turning the loader from a `bool` into a 3-value `tier` projection. A separate file would fork prose (violates NR-1). Now mandated explicitly. |
| OQ-6: `KickoffState` may need a `persona` field. | `KickoffState.to_dict` is the **extraction** payload, orthogonal to the guided experience. The real cross-surface contract is `build_guided_view` + `guided_parity_digest`, enforced byte-equal across CLI/web/TUI by `test_guided_experience_m4.py:155`. | Persona goes in the **guided view-model + parity digest**, never `KickoffState`. The existing parity test does not break — it *enforces* FR-14 (all surfaces render persona in lockstep). |
| FR-5: "never override explicit." | The ledger already records explicit decisions and `awaiting_fields` already excludes ledgered fields (`confirm_walk.py:69`). | FR-5 is **nearly free**: a pre-pass that only touches unledgered fields inherits the guarantee. |

**Resolved open questions:**
- **OQ-1 → posture has NO store.** Persona rides the `guided` preference ladder instead (see FR-1).
- **OQ-2 → ledger, not FieldDef.** `audience-default:<slug>` extends the ledger entry; bump schema to v2.
- **OQ-3 → delimiter-region model required.** Feasible only as marked regions in the same doc (FR-9).
- **OQ-4 → filter is trivial, but writing needs a pre-pass.** `awaiting_fields` gains one predicate; a new `apply_audience_defaults` does the writing (FR-11).
- **OQ-5 → new `audience_defaulted` count bucket.** Otherwise audience-defaults masquerade as human-confirmed in `domain_confirmation` (FR-13).
- **OQ-6 → guided view-model + parity digest, not `KickoffState`.** (FR-14.)
- **OQ-7 → `manifest.py` config layer.** Profiles are in-process data (`AUDIENCE_PROFILES`), not packaged/downloaded files.

### 0.1 Lessons-Learned Hardening (v0.3)

> Applied the SDK lessons (phantom-reference audit, overloaded-term co-location, single-source
> vocabulary ownership, CRP steering) before external review. Two changed the draft materially:

- **[Phantom-reference audit]** — grepped every existing symbol the spec leans on. All verified
  (`resolve_guided_preference` `guided_routing.py:113`, `BuildPreferencesManifest`
  `kickoff_inputs/build_preferences.py:28`, `PROVENANCE_DEFAULTS` `manifest.py:38`, `LEDGER_SCHEMA`
  `confirmation.py:33`, `domain_confirmation` `confirmation.py:150`, `load_experience_doc`
  `writes.py:130`, `get/set_preference` `config.py:299/303`) **except a path error**: the FR-14
  anchors `build_guided_view` / `guided_parity_digest` live in
  **`kickoff_experience/concierge_view.py`** (`:675` / `:719`), not `concierge/concierge_view.py`.
  Corrected in the plan. New symbols (`resolve_audience_preference`, `apply_audience_defaults`,
  `AUDIENCE_PROFILES`) are to-be-created and marked as such.
- **[Overloaded-term co-location] — MATERIAL.** "persona" is **already an owned term** in this
  codebase (**319 occurrences**): in `stakeholder_panel/`, `requirements_panel/`, `persona_drafting`,
  `cli_panel.py`, a *persona* is a **synthetic stakeholder/reviewer voice queried from a roster**.
  This feature's "persona" (the human user's software-fluency archetype) is a **second, unrelated
  meaning**. Per the lesson, the new concept must **not** co-locate under the same bare identifier —
  a `concierge/persona.py` beside `persona_drafting` would actively mislead. **Hardening applied:**
  all symbols for this feature are namespaced to a distinct term (**`audience`** — `KickoffAudience`
  enum, `audience.py`, `AUDIENCE_PROFILES`, `resolve_audience`), reserving "persona" for the existing
  roster concept. **RESOLVED (OQ-12): the user-facing label is also `audience`** — `startd8 kickoff
  audience` — so code and CLI share one collision-free term. (The prose in §0.1/§0.2/OQ-12 still says
  "persona" *where it denotes the stakeholder-panel roster concept under discussion*; see the
  terminology banner below §0.2.)
- **[Single-source vocabulary ownership]** — this doc is the **owner** of the audience/fluency model
  and the two-knob (disclosure × surface) vocabulary; it *cites* (does not restate) the
  content-contract single-source rule and the `posture` axis, which are owned elsewhere. No drift
  introduced.
- **[CRP steering]** — both docs are brand-new (least-reviewed). The CRP target is
  `PERSONA_EXPERIENCES_REQUIREMENTS.md`; settled/do-not-relitigate items (the 3 user decisions,
  persona-as-lens, orthogonality-to-posture, byte-identity guardrail) are carried in
  `crp-focus-kickoff-persona-experiences.md`.

### 0.2 Panel Dogfood Findings (v0.4)

> **Recursive dogfood:** we ran the SDK's own adversarial stakeholder panel
> (`startd8 kickoff panel ask-all`, Sonnet) with a roster of the **three proposed audiences embodied
> as end-users** (`docs/kickoff/inputs/stakeholders.yaml`). Each critiqued this very doc from its
> lived perspective. Findings are SYNTHETIC/UNRATIFIED (the tool flags them so) but several were
> clearly correct and are folded in below. Full transcript persisted to `.startd8/transcripts/`.

| Finding | Audience | Resolution |
|---------|----------|-----------|
| No requirement for the beginner "we filled some things in — here's where to change them" moment | Beginner | **New FR-15** |
| No in-session "show me everything now" escape hatch (undo the pre-pass mid-session) | Beginner | **New FR-16** |
| `audience_defaulted` bucket silently changes the `assess` display even for unset/Intermediate users | Intermediate | **FR-13 fix** (display byte-identity when no audience defaults exist) |
| Provenance shown in ledger/assess but not LIVE in the walk where decisions are made | Intermediate | **New FR-17** |
| FR-2/FR-4 byte-identity asserted, not demonstrated — name the test + merge gate | Int + Adv | **FR-4 sharpened** |
| Confirm-all is a blind batch write — needs a dry-run / pre-commit diff | Advanced | **New FR-18** |
| OQ-12 mis-prioritized: collision is a correctness decision, not a warmth call | Advanced | **Resolved → user chose user-facing `audience`** (the veteran archetype's objection won) |

### 0.3 Canonical terminology (read before reviewing)

> **CANONICAL TERM: `audience`.** The user-facing CLI verb (`startd8 kickoff audience`) and **all**
> code symbols (`KickoffAudience`, `audience.py`, `AUDIENCE_PROFILES`, `resolve_audience`,
> `apply_audience_defaults`, `audience_defaulted`, `audience-default:<slug>`) use `audience`. This
> resolves the ×319 "persona" overload (OQ-12) — **`persona` is reserved for the `stakeholder_panel`
> roster concept.** The word "persona" still appears in this doc **only** in §0.1/§0.2 and OQ-12,
> where it deliberately denotes that roster concept under discussion. The **filename/title retain
> "Persona"** for git/reference continuity; a cosmetic file rename is a tracked follow-up, not a
> blocker.

---

## 1. Problem Statement

The `startd8 kickoff` experience was distilled from overlapping tools (welcome-mat, red-carpet)
into **one** kernel + **one** guided experience, with a hard-won **render-only, single-source**
content contract (no prose forks) and a **SOTTO byte-identity** guarantee.

The one guided experience is calibrated for a single implicit user: someone *familiar with
software*. It over-explains for a veteran (prose is noise; they want the field list and to edit
everything) and under-scaffolds for a newcomer (unfamiliar vocabulary — "observability",
"conventions", "schema contract" — presented as decisions they can't meaningfully make).

We want **persona-tailored** project-start experiences for three archetypes:

| Persona | Archetype | Needs |
|---------|-----------|-------|
| **Beginner** | new to software | plain-language framing, shielded from decisions they can't make, strong safe defaults, reassurance/reversibility |
| **Intermediate** | familiar with software | today's guided walk — all domains, light "why", pre-filled defaults |
| **Advanced** | software veteran | terse, full decision surface, all defaults visible & editable, confirm-all efficiency, prose suppressed |

### Gap table

| Component | Current State | Gap |
|-----------|--------------|-----|
| Experience selection | Only `posture` (prototype/production), a *trust/authority* axis — **and not even persisted** (per-invocation flag) | No *fluency* axis; one-size guided walk |
| Preference persistence | The `guided` tri-state ladder DOES persist a per-project changeable preference (`build-preferences.yaml` → global config → default) | No `persona` field on that ladder |
| Prose density | Single binary `compact` slice in `load_experience_doc` | No 3-tier projection; no plain-language region authored |
| Decision surface | All 4 input domains always exposed by `awaiting_fields` | No persona filter; no write-the-shielded pre-pass |
| Decision provenance | Ledger records `{value, at, mode ∈ set|as-is}` | No `audience-default:<slug>` provenance; `domain_confirmation` can't distinguish it |

## 2. Design Model (normative framing)

Persona is a **lens over the ONE canonical experience**, never three parallel experiences. Same 4
input domains, same fields, same `confirmed.yaml` ledger. Persona is **orthogonal** to `posture`
(fluency axis ⟂ trust axis); we do **not** build a 3×2 matrix of experiences.

Persona resolves to **two orthogonal knobs**:

- **DISCLOSURE** — prose density, projected from a single source at 3 tiers (compact / light / expanded).
- **SURFACE** — how many decisions are *exposed for prompting* vs. *silently sound-defaulted-and-written*.

| Persona | Disclosure tier | Surface |
|---------|-----------------|---------|
| Beginner | `expanded` (plain-language) | Reduced (pre-pass writes shielded defaults; walk prompts the remainder) |
| Intermediate | `light` (today's walk) | Full, pre-filled — **byte-identical to today** |
| Advanced | `compact` (per-field prose suppressed) | Full, all defaults visible + confirm-all |

**Key non-obvious point:** Beginner is *not* the opposite of Advanced. Beginner = expanded prose +
*reduced* surface; Advanced = compact prose + *full* surface. Different corners of a 2×2, not two
ends of one slider.

## 3. Requirements

### Selection & persistence
- **FR-1** *(revised — D-1)* Persona is an explicit, project-remembered, changeable selection that
  rides the **existing `guided` preference ladder**: resolved flag → project `build-preferences.yaml`
  `persona:` → global `~/.startd8/config.json` `preferences.persona` → default. It does **not**
  mirror `posture` (which has no store). Add a `persona` field to `BuildPreferencesManifest` and a
  `resolve_audience_preference` clone of `resolve_guided_preference`.
- **FR-2** Default persona (when unset) is **Intermediate** — today's guided walk — so existing
  behavior is byte-identical for anyone who never picks a persona.
- **FR-3** A user can view and change the current persona (`kickoff audience [show | set <slug>]`),
  writing the project and/or global preference exactly as the `guided` preference is written.

### Byte-identity / provenance guardrail
- **FR-4** *(sharpened — panel I1/A2)* Persona is a **presentation + default-selection** projection
  only. Given the **same explicit decisions**, output (`inputs/`, `confirmed.yaml` values) is
  **byte-identical** across personas. This is not merely asserted: a **named golden test**
  (`test_audience_byte_identity`) drives a fixed explicit-decision script under all three audiences
  and asserts identical output, and the M5 acceptance gate **blocks merge if that test is absent or
  failing**. (Property emerges from FR-5 + FR-9; the test is the proof the reviewer can point at.)
- **FR-5** *(nearly free — D-7)* Persona-chosen defaults fill **unledgered** fields only; the
  pre-pass skips any `value_path` already in `confirmed_value_paths`, so persona **never overrides an
  explicit choice**.
- **FR-6** *(revised — D-3)* Every persona-written value carries **ledger** provenance distinguishing
  it from an explicit confirmation: extend the ledger entry (`confirmed.yaml`) with a
  `audience-default:<slug>` provenance and bump `LEDGER_SCHEMA` to `kickoff.confirmed.v2`
  (backward-tolerant load). The closed `FieldDef.PROVENANCE_DEFAULTS` set is **not** touched.

### Per-persona default profiles
- **FR-7** *(sited — OQ-7)* Each persona has a **default profile** in the `manifest.py` config layer
  (`AUDIENCE_PROFILES: dict[slug, dict[value_path, value]]`) — a single-source, in-process
  field→value table consulted when a field is unledgered. Not a packaged/downloaded file.
- **FR-8** Default profiles are **partial**: a persona specifies only the fields where it differs
  from the base; unspecified fields inherit the base `FieldDef` default behavior. `lint_config`
  gains a check that every profile `value_path` exists in the config.

### Disclosure knob
- **FR-9** *(revised — D-5, drift trap)* The content loader surfaces prose at the persona's
  disclosure tier via a **single-source projection**: change `load_experience_doc(key, *,
  compact: bool)` to `tier ∈ {compact, light, expanded}`, where the `expanded` (plain-language)
  content is authored as **additional delimiter-marked regions inside the same doc**
  (`<!-- PLAIN -->…<!-- /PLAIN -->`). Authoring the expanded tier in a **separate file is
  prohibited** (would fork prose, violating NR-1).
- **FR-10** Beginner disclosure renders plain-language framing for domain "why"/"what"; Advanced
  suppresses per-field `why`/`grammar` lines in `field_prompt_lines`.

### Surface knob
- **FR-11** *(revised — D-4)* Beginner **reduces** the prompted surface via a **pre-pass**
  (`apply_audience_defaults`) that, for each reduced-surface field not yet in the ledger, writes the
  persona default through the existing `build_confirm_plan` + `apply_confirm` machinery (tagged
  `audience-default:<slug>`). The written fields then drop out of the **unchanged** `awaiting_fields`;
  the walk prompts only the remainder. Shielded decisions are **written, never omitted** (never a
  reduced contract).
- **FR-12** *(scoped — batch of existing as-is)* Advanced exposes the **full** surface with a
  **confirm-all** path: a batch loop over `awaiting_fields` calling `build_confirm_plan(mode="as-is")`
  + `apply_confirm` for each (reuses the single-field `--as-is` machinery that already exists). Gated
  by the FR-18 pre-commit preview. **(sharpened — panel A2)** A **named test**
  (`test_confirm_all_equals_single`) MUST assert the batch path produces **byte-identical ledger
  entries** to N single-field `--as-is` confirmations — proving "reuses" is not a second code path
  that can drift.
- **FR-13** *(revised — OQ-5)* An audience-defaulted field must be **distinguishable from a human
  confirmation** so a beginner can later reach shielded decisions: `domain_confirmation` gains an
  `audience_defaulted` bucket (routed by the FR-6 provenance) instead of counting them as
  `confirmed`; `assess` surfaces it; `kickoff confirm <vp>` re-writes an audience-default into an
  `explicit` confirmation. **(fix — panel I2)** When **no** audience-default entries exist on disk
  (the unset/Intermediate case), `domain_confirmation`/`assess` output is **byte-identical to today**
  — the new bucket is empty/omitted, so users who never touch audience see **no display regression**.
  (Extends FR-2/FR-4 byte-identity to the reporting surface.)

### Panel-derived (v0.4 — from the audience dogfood)
- **FR-15** *(Beginner B2)* When the pre-pass (FR-11) writes shielded defaults, the reduced-surface
  experience MUST surface a **plain-language reassurance moment**: "we filled in N things for you —
  here's where to see and change them." The mechanism (FR-6/FR-13) is not enough; the *user-facing
  communication* is itself a requirement.
- **FR-16** *(Beginner B4)* A user MUST have an **in-session escape hatch to expand the surface now**
  ("show me everything") — reversing the reduced-surface shielding for the current session, distinct
  from changing the audience preference for the *next* session (FR-3). Reversal converts
  audience-default fields back to `awaiting` (or re-prompts them); it never clobbers an `explicit`
  value (FR-5).
- **FR-17** *(Intermediate I4)* The confirm **walk itself** — not only `assess` after the fact — MUST
  render a **live per-value provenance indicator** distinguishing an audience-defaulted value from
  one the user explicitly accepted, at the prompt where the decision is made. (Ledger provenance FR-6
  is the data; this is its surfacing at the point of decision.)
- **FR-18** *(Advanced A4)* The Advanced **confirm-all** path (FR-12) MUST offer a **pre-commit
  preview / `--dry-run`**: show the full field→value table that will be batch-written and require a
  single explicit confirmation before `apply_confirm` runs. A blind bulk sweep over `awaiting_fields`
  is prohibited — it is indistinguishable from the tool making choices for the user.

### Surface parity (CLI / TUI / web)
- **FR-14** *(sited — OQ-6)* Persona applies identically across CLI, TUI, and web by adding a
  `persona` block to `build_guided_view` and a `persona` key to `guided_parity_digest`
  (alongside the existing `posture` block). The existing byte-equal parity test enforces lockstep;
  `KickoffState` is **not** touched.

## 4. Non-Requirements

- **NR-1** No three parallel experiences / no prose forks. Persona is a lens; the expanded
  disclosure tier MUST be same-doc marked regions (FR-9), not a second file.
- **NR-2** No automatic persona **inference** from git/code signals in v1 (explicit selection only).
- **NR-3** Persona does **not** replace or subsume `posture`; the two remain orthogonal.
- **NR-4** No new input domains, no `.prisma`/contract change, no change to what an app *is* — only
  the path to the same kickoff inputs.
- **NR-5** No persona-specific *widgets* or wholly new UI components in v1 (reuse the confirm-walk
  and existing surfaces).
- **NR-6** *(new)* No change to `KickoffState.to_dict` (the extraction payload) — persona lives only
  in the guided view-model.

## 5. Open Questions (post-planning)

- **OQ-8** Provenance encoding in the ledger entry: a **new `mode` value** (`mode: "audience-default"`
  plus a `persona:` key) vs. an **additive `provenance` field** on the existing entry. Which is more
  backward-tolerant for existing `v1` ledgers on disk? (Leaning additive `provenance` field.)
- **OQ-9** For Beginner reduced surface, *which specific fields/domains* are shielded? Is it
  domain-granular (e.g. shield all of `observability` + `conventions`) or field-granular? (Affects
  the `AUDIENCE_PROFILES` shape and the `awaiting_fields` predicate.)
- **OQ-10** Should `kickoff audience set` re-run the pre-pass immediately (apply beginner defaults on
  switch) or only affect the *next* guided invocation? (Idempotency + surprise-write concern.)
- **OQ-11** Does the web surface need a persona selector control in v1, or is persona set via
  CLI/preference and merely *rendered* by web? (Scope of the M5 parity work.)
- **OQ-12 → RESOLVED (user, post-panel).** **User-facing label = `audience`** (`startd8 kickoff
  audience`), matching the code namespace — one collision-free term for both surfaces. The panel
  dogfood elevated this from a warmth call to a correctness decision: the **veteran archetype** — the
  person most likely to use both this and the `stakeholder_panel` `persona` roster commands — argued
  that keeping user-facing "persona" would confuse in help text. The user accepted that argument over
  the earlier "keep persona" preference. See §0.3 for the canonical-terminology rule.

---

*v0.3 — Post lessons-learned hardening. Applied 4 lessons: phantom-reference audit (caught a
`concierge/` vs `kickoff_experience/` path error on the FR-14 anchors), overloaded-term co-location
(MATERIAL — "persona" is an owned term ×319; code namespaced to `audience`, OQ-12 raised for the
surface word), single-source vocabulary ownership (clean), CRP steering (target + focus file named).*

*v0.4 — Post persona-panel dogfood. Ran the SDK's own adversarial stakeholder panel with the three
proposed personas embodied as end-users, reviewing this doc. Folded in FR-15 (beginner reassurance
moment), FR-16 (in-session surface-expand escape hatch), FR-17 (live provenance in the walk), FR-18
(confirm-all dry-run); sharpened FR-4/FR-12 to name their guardrail tests; fixed FR-13 (no display
regression for non-audience users); elevated OQ-12 (the veteran archetype argues against the "keep
persona" default — needs a user decision).*

*v0.5 — OQ-12 RESOLVED by the user: user-facing label = `audience` (the veteran archetype's
correctness objection won over the earlier "keep persona" steer). Renamed all code-symbol tokens
persona→audience for one collision-free term; added §0.3 canonical-terminology banner; `persona`
now denotes ONLY the `stakeholder_panel` roster concept (in §0.1/§0.2/OQ-12). Filename/title retain
"Persona" pending a cosmetic follow-up rename. Ready for CRP review.*
