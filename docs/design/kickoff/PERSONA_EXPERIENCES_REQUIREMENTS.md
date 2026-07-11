# Kickoff Persona Experiences — Requirements

**Version:** 0.9 (FR-16/FR-17 formally deferred post-v1 — see §3.3)
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
- **FR-16** *(Beginner B4)* **⏸ DEFERRED (post-v1) — see §3.3.** A user should have an **in-session
  escape hatch to expand the surface now** ("show me everything") — reversing the reduced-surface
  shielding for the current session, distinct from changing the audience preference for the *next*
  session (FR-3). Reversal converts audience-default fields back to `awaiting` (or re-prompts them);
  it never clobbers an `explicit` value (FR-5).
- **FR-17** *(Intermediate I4)* **⏸ DEFERRED (post-v1) — see §3.3.** The confirm **walk itself** — not
  only `assess` after the fact — should render a **live per-value provenance indicator** distinguishing
  an audience-defaulted value from one the user explicitly accepted, at the prompt where the decision
  is made. (Ledger provenance FR-6 is the data; this is its surfacing at the point of decision.)
- **FR-18** *(Advanced A4)* The Advanced **confirm-all** path (FR-12) MUST offer a **pre-commit
  preview / `--dry-run`**: show the full field→value table that will be batch-written and require a
  single explicit confirmation before `apply_confirm` runs. A blind bulk sweep over `awaiting_fields`
  is prohibited — it is indistinguishable from the tool making choices for the user.

### Surface parity (CLI / TUI / web)
- **FR-14** *(sited — OQ-6; §0.3-corrected)* Audience applies identically across CLI, TUI, and web by
  adding an **`audience`** block to `build_guided_view` and an **`audience`** key to
  `guided_parity_digest` (alongside the existing `posture` block). The existing byte-equal parity test
  enforces lockstep; `KickoffState` is **not** touched. Acceptance: `grep -n '\bpersona\b'` on the new
  code in `concierge_view.py` returns 0 (§0.3 canonical term).

## 3.1 Post-CRP Amendments (v0.6)

> Triaged the R1 (opus) + R2 (sonnet adversarial) rounds in Appendix C. All accepted (they falsify
> real claims or close real gaps); dispositions in Appendix A. These amend the FRs above.

- **A-FR4 (R1-F2, R2-F20/F21/F22) — the byte-identity guarantee is redefined precisely.** Split the
  two artifacts: **`inputs/*.yaml` = byte-identical** across audiences (they carry no metadata);
  **`confirmed.yaml` = VALUE-identical** per `value_path`, explicitly **excluding** the metadata
  fields `at`, `mode`, and `provenance` (which legitimately differ by path). `test_audience_byte_identity`
  MUST (a) assert full-byte equality of `inputs/`, and (b) assert value-only equality of the ledger
  after normalizing out `at`/`mode`/`provenance` and audience-default-only entries. Add a **second
  golden**: a *partial-explicit* fixture (decide subset S explicitly, let the rest audience-default
  under Beginner) AND a *pre-pass-then-promote* timeline fixture (Beginner pre-pass persists, then all
  fields promoted via `kickoff confirm`) — both compared against an Intermediate-direct run. This is
  the timeline the fresh-start script misses.
- **A-FR6 (R1-F1, R2-F25, R1-S4) — conditional schema bump + backward-compat contract.** The ledger
  stays `kickoff.confirmed.v1` until the **first `audience-default` provenance is actually written**;
  only then is it rewritten `v2`. So a user who never sets an audience gets **zero** file change
  (preserves FR-2). Provenance-absence is normative: **absence of `provenance` ⇒ explicit/human** — so
  v1 files and pre-existing entries route to `confirmed`, never `audience_defaulted`. Add the
  compatibility table to the spec: {v2-code×v1-file → load clean, treat as explicit; v2-code×mixed →
  valid; **v1-code×v2-file (rollback) → v1 reader must not crash: unknown provenance keys are ignored,
  schema-version mismatch tolerated read-only**}. Name which writes trigger the bump (only an
  audience-default write).
- **A-FR6b (R2-F22) — explicit promotion strips provenance.** `kickoff confirm <vp>` promoting an
  audience-default to explicit MUST remove the `provenance` key (and set `mode: set`), so the resulting
  entry is **indistinguishable** from a direct explicit confirmation — otherwise A-FR4 value-equality
  is impossible.
- **A-FR9 (R1-F3, R2-F23) — disclosure is co-located per-region variants, and the NR-1 claim is made
  honest.** Beginner plain-language is **substitutive** (rewords the same concept inline), which an
  append-only `<!-- PLAIN -->` block cannot do. Model each disclosure unit as a **co-located region
  carrying up to three tier variants** (compact/light/expanded); the loader selects one; a region
  lacking `expanded` **degrades to `light`**. NR-1 is restated honestly: single-source means *one
  file*, but the in-file variants can still drift, so the guard is **structural + a superset/freshness
  test**, NOT a mere file-count check: a lint MUST assert every region resolves at all three tiers AND
  that `tier=expanded` is a content-superset of `tier=light` (or each variant carries a checksum of the
  light prose it shadows). *(This is the single largest post-CRP change; it converts FR-9 from an
  under-specified claim into an enforceable one.)*
- **A-FR12 (R2-F28) — "extends", not "reuses".** FR-18's pre-commit preview forces a **two-phase
  collect-all-plans-then-apply** shape the interleaved single-field path lacks. FR-12 therefore
  **extends** (not reuses) the `--as-is` machinery; `test_confirm_all_equals_single` asserts the
  preview is a **no-op on ledger bytes** vs N single confirms.
- **A-FR13 (R2-F26) — omit the empty bucket + M2 gate.** `domain_confirmation` MUST **omit** the
  `audience_defaulted` key entirely when zero (not emit `audience_defaulted: 0`), else `assess` output
  regresses for every non-audience user. Add named test **`test_assess_no_audience_regression`** as an
  **M2 merge gate** (not M5).
- **A-FR16 (R1-F4, R2-F24) — mechanics fully specified.** "Expand surface now" **deletes** the
  audience-default ledger entries (the only cross-session-viable op) and re-prompts them in the current
  walk. If the user quits mid-expand, the abandoned fields are `awaiting` (documented; a Beginner
  re-entry re-runs the pre-pass and re-shields them, an Intermediate re-entry prompts them). The
  pre-pass MUST record fields **un-shielded this project** and **skip re-shielding them**; a switch to a
  **broader-surface audience re-opens** audience-defaulted fields (Advanced promises all defaults
  visible). Pre-pass is **idempotent**: a second run writes nothing and never bumps an existing `at`.
- **A-FR17 (R1-F6) — parity-bound.** The live in-walk provenance indicator flows through
  `build_guided_view` + `guided_parity_digest`, so the byte-equal parity test enforces it across
  CLI/TUI/web (not a CLI-only affordance).
- **A-OQ9 (R1-F5) — shieldability criterion (resolves OQ-9).** A field is **shieldable only if it has
  a safe, universally-reasonable, reversible default**; fields without one are **always prompted, even
  for Beginner**. `lint_config` validates every `AUDIENCE_PROFILES` entry against a safe-default
  allowlist. (Granularity: domain-level default *sets*, field-level shieldability gate.)
- **A-OQ8 — resolved** by the A-FR6 compatibility table (encoding = additive `provenance` field; bump
  conditional; rollback tolerated read-only).
- **A-OQ10 (resolves OQ-10) — deferred pre-pass.** `set` = preference-only; the pre-pass fires at
  **walk-start** (explicit write action), never on a read/GET. One canonical setter
  (`set_audience_preference`) is the sole preference writer; CLI `audience set` and web (FR-19) both
  call it. This is the single pre-pass trigger site the idempotency test (R2-S21) and A-FR16 assume.
- **A-FR19 (new; resolves OQ-11) — web audience selector, guarded.** The web surface exposes an
  interactive selector that **persists** the audience by calling the **same** `set_audience_preference`
  as the CLI — it is **not** a second preference-write path. It rides the existing `web.py` write
  guards (CSRF token + Origin check + session + rate-limit, the same class as the capture-apply
  endpoint), validates input against the `KickoffAudience` enum, and — per A-OQ10 — writes **only the
  preference** (the pre-pass fires later at walk-start, on an explicit POST, not on the selector write
  or any render). The rendered effective-audience + selector state flow through `build_guided_view` /
  `guided_parity_digest` (FR-14) so CLI/TUI/web stay in lockstep. **Because this is the riskiest
  surface, FR-19 carries an explicit M5 security-review gate** (precedent: the consult `--serve`
  CRP-hardening).

## 3.2 Post-CRP Amendments — R3/R4 (v0.8)

> Triaged the R3 + R4 rounds (Appendix C), both `claude-opus-4-8` external runs — R4 a **builder's-eye**
> review by the agent who implemented the ledger/walk substrate, verified against `origin/main` after
> PRs #115/#116/#117 that **post-date this doc's planning pass**. All six accepted (two are new HIGH
> integration bugs from same-day merges). Dispositions in Appendix A.

- **A-FR9b (R3-F30) — the tier loader must compose with post-#115 `load_experience_doc`.** The live
  signature is `load_experience_doc(key, *, compact=False, section=None)` with
  `_SLICE_MARKERS = (<!-- TL;DR -->, <!-- BANNER -->)` and a **silent fall-back-to-full-doc** on a
  missing region (`concierge/writes.py`). A-FR9's tier work MUST: (a) make `tier` **orthogonal to and
  compose with** the existing `section=` axis (a banner is not a disclosure tier); (b) **register** the
  new tier/`<!-- PLAIN -->` (or per-region-variant) markers in `_SLICE_MARKERS`, or Beginner prose
  **leaks into `explain`/full-render** (which strips only registered markers); (c) **replace** the
  loader's silent full-doc fallback with A-FR9's fail-closed **degrade-to-light** — never serve raw
  un-tiered prose to a Beginner; (d) refresh the stale `writes.py:126` "binary slice / no third region"
  citations in §0/FR-9. **This makes A-FR9 implementable against real code.**
- **A-FR6c (R3-F31) — fail-open provenance is a *tested write-path invariant*.** A-FR6's "absence of
  `provenance` ⇒ explicit" is fail-*open* (untagged → most-authoritative bucket), safe only if **every**
  non-explicit writer stamps provenance. Make it normative: every ledger writer other than
  `kickoff confirm` (the FR-11 pre-pass + any future machine writer) MUST stamp `provenance`; add named
  test **`test_prepass_writes_are_provenance_tagged`** + an AST/grep check that no non-`confirm` write
  path omits it.
- **A-FR11b (R4-F32) — pre-pass vs the present-file gate (PR #116), HIGH.** `awaiting_fields` now
  surfaces a field **only if its input YAML exists** (`confirm_walk.py:_input_file_present`), and
  `apply_audience_defaults` writes via `build_confirm_plan`, which **splices into that file**. So a
  Beginner who sets audience **before `kickoff instantiate`** (or on a partial project) gets a pre-pass
  that writes nothing and is **silently full-surfaced** — breaking FR-11 with no error. **Fix:** the
  pre-pass MUST be **fail-closed** — `kickoff instantiate` is a documented precondition; if inputs are
  absent the walk-start either instantiates-then-shields or refuses with a message, **never silently
  full-surfaces.** The FR-11 golden MUST include an un-instantiated start.
- **A-FR12b (R4-F33) — no `as-is` over placeholder defaults, HIGH.** On-disk template defaults are
  literal placeholders (`budgets.per_pipeline_run = "$<5.00>"`, `monetization.mode_now =
  <free-during-demo | live>`). `build_confirm_plan(mode="as-is")` records the on-disk value, so
  confirm-all-`as-is` (FR-12) would ledger the **placeholder string** — and an invalid `select` choice.
  FR-12/FR-18 MUST **skip or reject** a field whose on-disk value matches a `<…>`/placeholder pattern
  (leave it `awaiting` with guidance), not just surface it in the FR-18 dry-run. Test: `test_confirm_all_*`
  asserts a placeholder-valued field is **not** batch-confirmed.
- **A-FR13b (R4-F34) — bucket precedence vs `stale`.** `domain_confirmation` already returns
  `{confirmable, confirmed, awaiting, stale}`. Define precedence for an audience-default whose on-disk
  value later diverged: it is **`audience_defaulted` with a `stale` flag** (not double-counted), and the
  buckets MUST **partition** the confirmable set (Σ == `confirmable`). Add a partition-invariant test.
- **A-FR6d (R4-F35) — the conditional bump's exact edit site.** `_dump_ledger` writes
  `schema: LEDGER_SCHEMA` **unconditionally** (`confirmation.py`). A-FR6's "stay `v1` until the first
  `audience-default`" is one edit at that single writer: emit `v1` unless the map contains an
  `audience-default` entry, else `v2`. Test: an all-explicit ledger serializes `schema:
  kickoff.confirmed.v1` byte-for-byte as today.

## 3.3 Deferred (post-v1) — FR-16 + FR-17 (refreshed 2026-07-10)

> **FR-16 (in-session expand-surface escape hatch) and FR-17 (live in-walk provenance indicator) are
> formally DEFERRED post-v1.** M1–M5 shipped without them; this section resolves the doc-vs-code drift
> (the spec previously claimed them for M3). Reassessed against `main` after ~248 commits of kickoff
> evolution — they are **still applicable and not superseded**, but their value has dropped. Build the
> pair *only if* the Beginner in-session un-shield flow is prioritized.

- **Still applicable (premise intact).** Beginner shielding still exists (`apply_audience_defaults`
  fires at walk-start, shielded fields drop from `awaiting_fields`), and the confirm **walk is still
  the primary place a user decides values**. Nothing built since supersedes either FR.
- **They are a coupled pair — ship together or not at all.** FR-17 has **nothing to render today**:
  a Beginner's shielded fields are dropped *out* of the walk, and Intermediate/Advanced have no
  audience-defaults — so an in-walk provenance indicator is **inert until FR-16 re-opens** shielded
  fields into the walk. FR-16, in turn, isn't safely usable unless the user can *see* which fields are
  shielded (FR-17). Neither makes sense alone.
- **The oracle/agentic layer added since drafting shrank FR-17's value.** The read-only
  oracle/agentic/`assess` surfaces now already show the aggregate `audience_defaulted` count (what the
  machine pre-filled). FR-17's remaining delta is narrow — *per-field, at the prompt* vs. an aggregate
  you check separately — i.e. **polish, not a gap**.
- **FR-16 target is unchanged: the walk/CLI.** It cannot move to the oracle surface — that surface is
  deliberately **read-only (CLI is the sole writer)**, and re-open *writes* (deletes ledger entries).
  So the original walk/CLI targeting stands; no reframing needed.
- **Reduced-priority rationale, one line:** *still coherent, premise intact, but must ship as a pair
  and the oracle layer already covers most of the underlying visibility need — hence LOW priority,
  post-v1.*

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
- **OQ-10 → RESOLVED (user): DEFERRED.** `kickoff audience set` (and the web selector, FR-19) writes
  **only the preference** — never the pre-pass. The pre-pass (`apply_audience_defaults`) and the
  widening re-open (A-FR16) fire when the user **begins the confirm walk** — an explicit write action
  (CLI `kickoff confirm` / guided walk start; web: an explicit POST). It **never fires on a read-only
  render/GET** — so a web guided-view page load does not write. One semantic trigger (walk-start),
  surface-independent; `set` stays a cheap, non-destructive preference write. *(See A-FR19 for how web
  honors this.)*
- **OQ-11 → RESOLVED (user): FULL WEB SELECTOR.** The web surface exposes an interactive audience
  selector that **persists** the choice (not render-only). This is the higher-scope path — it adds the
  web preference-write surface flagged as the riskiest part of interactive-kickoff — so it ships with
  mandatory guardrails; see **A-FR19**.
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
| R1-F2, R2-F20/F21/F22 | FR-4 byte-identity under-proven (metadata leak, pre-pass-then-promote timeline) | opus+sonnet | Applied §3.1 A-FR4: split inputs=byte / ledger=value-only; 2 new goldens | 2026-07-06 |
| R1-F1, R2-F25, R1-S4 | Unconditional v2 bump breaks FR-2; backward-compat unspecified | opus+sonnet | Applied §3.1 A-FR6: conditional bump + compat table + rollback | 2026-07-06 |
| R2-F22 | Provenance not stripped on explicit promotion | sonnet | Applied §3.1 A-FR6b | 2026-07-06 |
| R1-F3, R2-F23 | FR-9 in-file variant still forks; NR-1 claim unenforced | opus+sonnet | Applied §3.1 A-FR9: co-located tier variants + superset lint | 2026-07-06 |
| R2-F28 | FR-12 "reuses" wrong; FR-18 forces two-phase | sonnet | Applied §3.1 A-FR12: "extends" + preview no-op test | 2026-07-06 |
| R2-F26 | FR-13 non-regression untested; `audience_defaulted:0` leaks | sonnet | Applied §3.1 A-FR13: omit empty key + M2 gate test | 2026-07-06 |
| R2-F27 | FR-14 `persona` key violates §0.3 | sonnet | Applied inline to FR-14 (→`audience` key + grep gate) | 2026-07-06 |
| R1-F4, R2-F24 | FR-16 mechanics undefined; re-shield hazard | opus+sonnet | Applied §3.1 A-FR16 | 2026-07-06 |
| R1-F6 | FR-17 not parity-bound | opus | Applied §3.1 A-FR17 | 2026-07-06 |
| R1-F5 | OQ-9 needs shieldability criterion | opus | Applied §3.1 A-OQ9 (resolves OQ-9) | 2026-07-06 |
| R3-F30 | FR-9/A-FR9 specced vs pre-#115 loader (section=, marker registration, fallback) | opus-4-8 | Applied §3.2 A-FR9b | 2026-07-06 |
| R3-F31 | Fail-open provenance default unenforced | opus-4-8 | Applied §3.2 A-FR6c (+ named test) | 2026-07-06 |
| R4-F32 | Pre-pass collides with present-file gate (#116) → silent full-surface | opus-4-8 (builder) | Applied §3.2 A-FR11b (fail-closed precondition) | 2026-07-06 |
| R4-F33 | confirm-all `as-is` over `<…>` placeholder writes garbage | opus-4-8 (builder) | Applied §3.2 A-FR12b (skip/reject placeholders) | 2026-07-06 |
| R4-F34 | `audience_defaulted` vs `stale` bucket precedence undefined | opus-4-8 (builder) | Applied §3.2 A-FR13b (partition invariant) | 2026-07-06 |
| R4-F35 | `_dump_ledger` writes schema unconditionally | opus-4-8 (builder) | Applied §3.2 A-FR6d (exact edit site) | 2026-07-06 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — general-purpose (opus) — 2026-07-06

- **R1-F1** *(FR-6/FR-2/OQ-8, Data, high)* Unconditional `v1→v2` schema bump rewrites the schema line in `confirmed.yaml` for users who never touch audience → breaks FR-2 byte-identity at that line. Keep `v1` until the FIRST `audience-default` is written; only then rewrite `v2`.
- **R1-F2** *(FR-4, Validation, high)* The golden drives an all-explicit script → the pre-pass is a no-op, so byte-identity is tautological and the real leak (audience-default entries perturbing YAML ordering of sibling entries) is never exercised. (a) State the comparison is VALUES-only, excluding `at`/provenance; (b) add a partial-explicit golden (decide subset S, let remainder audience-default under Beginner, assert S's values byte-identical after normalizing out metadata).
- **R1-F3** *(FR-9/NR-1, Architecture, high)* The `<!-- PLAIN -->` model is additive, but real beginner plain-language is SUBSTITUTIVE (rewords the same concept inline) — an appended region can't reword inline text, so the projection may be structurally unable to hold. Specify additive-vs-substitutive; for substitution mandate per-region co-located variants (each concept carries compact/light/expanded; loader selects; missing expanded→degrade to light) + a lint asserting every region resolves at all 3 tiers.
- **R1-F4** *(FR-11/FR-16/OQ-10, Risks, high)* Pre-pass skips ledgered fields, but FR-16 un-ledgers (back to awaiting) → a later pre-pass run RE-SHIELDS exactly what the user un-shielded, silently reversing "show me everything." Require the pre-pass to skip fields un-shielded this project/session; widening audience (Beginner→Advanced) must RE-OPEN audience-defaulted fields.
- **R1-F5** *(OQ-9/FR-8, Data, medium)* Silently writing a default for a project-specific field the Beginner never saw ships a wrong invisible decision. A field is shieldable ONLY if it has a safe, universally-reasonable, reversible default; else always prompted even for Beginner. `lint_config` validates every `AUDIENCE_PROFILES` entry against a safe-default allowlist.
- **R1-F6** *(FR-17/FR-14, Interfaces, medium)* FR-17's live provenance indicator isn't tied to the parity contract → CLI-only indicator diverges from web/TUI. Flow it through `build_guided_view`/`guided_parity_digest` so the byte-equal parity test enforces it across surfaces.

#### Review Round R2 — claude-sonnet-4-6 (adversarial) — 2026-07-06

- **R2-F20** *(FR-4, Validation, high)* "values byte-identical" is ambiguous: does `test_audience_byte_identity` compare full `yaml.dump` bytes or only each `value_path`'s `value` field? If field-extracted, entries with different `at`/`mode`/`provenance` still pass — proving nothing. Make the assertion explicit.
- **R2-F21** *(FR-4, Risks, critical)* Concrete break: Beginner pre-pass writes `{value:X, at:T0, mode:audience-default}`; user later promotes to explicit — does promotion set `at:T1` or preserve `at:T0`? Intermediate path has `at:T1`. A fresh-start fixed script never runs the pre-pass first, so the golden MISSES this. Add a "pre-pass-then-promote" timeline fixture.
- **R2-F22** *(FR-6/FR-13, Data, high)* Is the `provenance` field STRIPPED on explicit promotion? If preserved as history, promoted entry `{...,provenance:audience-default:beginner}` ≠ Intermediate entry `{...}` → not byte-identical. Mandate promotion strips/overwrites provenance so it's indistinguishable from a direct explicit confirm.
- **R2-F23** *(FR-9/NR-1, Architecture, high)* The same-doc region doesn't prevent a fork — it inlines one with NO freshness guarantee. Fix "light" prose, and the `<!-- PLAIN -->` variant silently goes stale; the file-count lint passes. Either mandate a superset/checksum test or honestly downgrade the NR-1-compliance claim to "authoring discipline + structural lint."
- **R2-F24** *(FR-16, Risks, high)* "converts back to awaiting (or re-prompts)" — the "or" hides two incompatible mechanics. Only ledger-delete survives session boundaries, but if the user quits before re-confirming, fields are in `awaiting` limbo → next Intermediate session prompts for un-shielded jargon. Also mid-session `domain_confirmation` shows 0 `audience_defaulted` while incomplete. Specify the exact op + abandoned-expand ledger state.
- **R2-F25** *(FR-6/OQ-8, Data, critical)* "backward-tolerant load" asserted not specified. Give a table code-version × file-version → behavior, incl. mixed-version files and the ROLLBACK case (v1 code reads v2 file) — the most dangerous, unaddressed. Specify exactly which writes trigger the bump (else 100% of M2 users get a surprise v2 upgrade).
- **R2-F26** *(FR-13, Validation, high)* No named test for the non-regression case. Naive impl always includes `audience_defaulted:0` → `yaml.dump` emits a new key for every non-audience user, breaking display byte-identity. Add `test_assess_no_audience_regression` as an M2 merge gate; omit the key entirely when empty.
- **R2-F27** *(FR-14/§0.3, Interfaces, high)* FR-14 adds a `persona` key to `build_guided_view`/`guided_parity_digest` — a NEW code symbol named `persona`, violating the §0.3 canonical rule that resolved OQ-12. Rename to `audience`. Acceptance: grep `\bpersona\b` on new code in `concierge_view.py` returns 0.
- **R2-F28** *(FR-12/FR-18, Interfaces, high)* FR-18's pre-commit preview forces collect-ALL-plans-then-apply; the single-field path interleaves plan+apply. So FR-12 "reuses" is wrong — the batch path needs a NEW two-phase collect-then-apply pattern. Say "extends" not "reuses"; ensure the preview is a no-op on ledger bytes for `test_confirm_all_equals_single`.

**Endorsements (cross-reviewer, raise triage priority):** R1-F2≡R2-F20/F21 (FR-4 under-proven); R1-F1≡R2-F25 (conditional bump/backward-compat); R1-F3≡R2-F23 (FR-9 fork not actually avoided); R2-F26 (FR-13 untested regression); R2-F27≡plan-S2 (FR-14 `persona` key violates §0.3).

#### Review Round R3 — claude-opus-4-8 — 2026-07-06

- **Reviewer**: claude-opus-4-8
- **Scope**: Fresh review weighted per the sponsor focus file, by a reviewer who **implemented and merged PR #115 (Kickoff UX output hygiene) earlier the same day** — which changed `load_experience_doc`, the exact function FR-9/A-FR9 rebuild. Read against `concierge/writes.py` @ `origin/main` (post-#115), the confirm-ledger machinery, and the R1/R2 dispositions in Appendix A. Settled items are **not** reopened; A-FR9/A-FR16/A-FR4/A-FR6 were verified as already covering several focus asks (noted below so they are not re-proposed).

##### Sponsor focus asks (answered first)

**Ask — FR-9 (disclosure without forking): is the same-doc region model sufficient?**
- **Summary answer:** The *model* is sound (A-FR9's co-located per-region tier variants + superset/freshness lint is right), but it is specified against a **stale snapshot of `load_experience_doc`** and will collide with code merged today.
- **Rationale:** FR-9 cites `writes.py:126` as "a **binary** slice, **no third region**." As of PR #115, `load_experience_doc(key, *, compact=False, section=None)` already has a **second axis** (`section=`) and a **third region** (`<!-- BANNER -->`), plus a `_SLICE_MARKERS` full-render strip. The tier rebuild must compose with `section=` (orthogonal: *which slice* × *disclosure tier*), and the current loader **falls back to the full doc** when a region is absent — the exact anti-pattern A-FR9's "degrade to light" must replace, not inherit.
- **Assumptions:** `origin/main` post-#115 is the implementation base.
- **Suggested improvement:** See **R3-F30**.

**Ask — FR-11 pre-pass ordering/idempotency vs confirm machinery + OQ-10.**
- **Summary answer:** Already resolved — no new suggestion.
- **Rationale:** A-FR16 makes the pre-pass idempotent ("a second run writes nothing and never bumps an existing `at`"), records fields un-shielded this project and skips re-shielding them, and specifies a broader-surface switch **re-opens** audience-defaulted fields — closing the persona-switch and re-shield hazards.
- **Assumptions:** A-FR16 is implemented as written.
- **Suggested improvement:** None — do not reopen.

**Ask — OQ-8 ledger provenance encoding + backward-tolerance.**
- **Summary answer:** The encoding decision (A-FR6 conditional bump + compat table + A-FR6b strip-on-promote) is solid; the residual risk is that the **fail-open default is unenforced**.
- **Rationale:** A-FR6 makes "absence of `provenance` ⇒ explicit/human" normative — fail-*open* (routes an untagged entry to the more-authoritative bucket), safe only while **every** non-explicit writer stamps provenance. Nothing makes that a tested invariant.
- **Assumptions:** the pre-pass (FR-11) and any future machine writer share the ledger.
- **Suggested improvement:** See **R3-F31**.

**Ask — OQ-9 which fields Beginner shields.**
- **Summary answer:** Adequately resolved by A-OQ9 (shieldable ⇔ safe/universal/reversible default + `lint_config` allowlist). No new suggestion.

**Ask — Byte-identity guarantee (FR-4): is a golden sufficient?**
- **Summary answer:** A-FR4's split (`inputs/` full-byte vs `confirmed.yaml` value-only-per-path, normalizing `at`/`mode`/`provenance`) + the partial-explicit and pre-pass-then-promote timeline goldens is sufficient; the entry-ordering concern is subsumed by the per-`value_path` comparison. No new suggestion.

##### Feature Requirements Suggestions

- **R3-F30** *(FR-9/A-FR9, Architecture/Interfaces, high)* The tier-loader rebuild is specified against a **pre-#115 `load_experience_doc`** and will collide with merged code. On `origin/main` the signature is `load_experience_doc(key, *, compact=False, section=None)` with a `<!-- BANNER -->` region and a `_SLICE_MARKERS` full-render strip (`concierge/writes.py`). A-FR9 must: (a) make `tier` **compose with** the existing `section=` axis rather than replacing `compact` in isolation (a banner is not a disclosure tier); (b) add the new tier/`<!-- PLAIN -->` (or per-region-variant) markers to **`_SLICE_MARKERS`**, or Beginner prose **leaks into `explain`/full-render** (that path strips only registered markers); (c) explicitly **replace** the loader's current silent **fall-back-to-full-doc** behavior with A-FR9's fail-closed "degrade to light" — the tier loader must never serve raw un-tiered prose to a Beginner (the shipped loader concretely exhibits the fallback hazard R2-F23/A-FR9 warned of); (d) refresh the stale `writes.py:126` "binary slice / no third region" citations. **Validation:** `tier=expanded` on a doc lacking an expanded variant yields the *light* variant (never the full doc); no tier marker survives a full/`explain` render.
- **R3-F31** *(FR-6/A-FR6/FR-11, Data/Validation, medium-high)* Make the fail-open provenance default enforceable. A-FR6 routes `provenance`-absent entries to `confirmed`/explicit — correct for legacy `v1` writers, but it silently **launders any future untagged write into a human confirmation**. Add a **normative write-path invariant** — every non-explicit ledger writer (the FR-11 pre-pass, any later machine writer) MUST stamp `provenance` — plus a named test (`test_prepass_writes_are_provenance_tagged`) asserting `apply_audience_defaults` **never** writes a `provenance`-less entry. This is the inverse of the codebase's own trust-tier fail-safe precedent (a missing trust marker must not default to the *most*-trusted tier unless a write-path invariant guarantees the marker is always present), so the guarantee must be explicit and tested, not assumed. **Validation:** an AST/grep check that every ledger write outside `kickoff confirm` supplies a provenance; the named test above.

**Endorsements (cross-reviewer):** none new — all R1/R2 items are already triaged into Appendix A; R3 raises only points unaddressed by the applied amendments.

#### Review Round R4 — claude-opus-4-8 — 2026-07-06

- **Reviewer**: claude-opus-4-8
- **Scope**: **Builder's-eye review** by the agent who implemented the substrate this feature rests on — the `confirmed.yaml` ledger + `build_confirm_plan`/`apply_confirm` (value-input confirmation, PRs #112/#113), the guided confirm walk + `awaiting_fields`/`domain_confirmation` (PR #114) **including the present-file gate merged TODAY (PR #116)**, `load_experience_doc` (content-contract), and the red-carpet-wizard retirement (PR #117). All findings below were **verified against `origin/main`** post-#115/#116/#117 (which post-date this doc's planning pass). Settled A/B items not reopened.

**Endorsements (validated against current code):**
- **R3-F30 (STRONGLY endorse — verified).** Confirmed the live signature is `load_experience_doc(key, *, compact=False, section=None)` with `_SLICE_MARKERS = (<!-- TL;DR -->, <!-- BANNER -->)`, a `section="banner"` slice, AND a silent **fall-back-to-full-doc** on a missing region (`concierge/writes.py`). All four R3-F30 asks are real; (b) marker-registration and (c) replace-the-fallback are the two that will otherwise leak Beginner prose or serve raw un-tiered prose. Apply before FR-9 is implementable.
- **R3-F31 (endorse).** The fail-open provenance invariant needs the named write-path test; correct precedent citation.

**New Feature Requirements Suggestions:**

- **R4-F32** *(FR-11/A-FR16, Risks, HIGH — new since planning)* **The pre-pass collides with the present-file gate merged today (PR #116).** `awaiting_fields` now surfaces a confirmable field **only if its input YAML exists on disk** (`confirm_walk.py:_input_file_present`), and `apply_audience_defaults` writes via `build_confirm_plan`, which **splices into that file** (requires it to exist). Consequence: the Beginner pre-pass can shield **only already-instantiated fields** — if a user sets Beginner before `kickoff instantiate`, or on a partial project, the pre-pass writes nothing and the Beginner silently gets the **FULL** surface, breaking the reduced-surface promise (FR-11) with no error. **Fix:** make `kickoff instantiate` a documented precondition of the pre-pass (fail-closed with a message if inputs absent), OR have the pre-pass instantiate-then-shield. Add a test: Beginner walk-start on an un-instantiated project either instantiates+shields or refuses — never silently full-surfaces. **Validation:** the FR-11 golden must include an un-instantiated start.
- **R4-F33** *(FR-12/FR-18, Data, HIGH)* **Advanced confirm-all-`as-is` over placeholder defaults writes garbage.** The confirmable fields' on-disk template defaults are literal placeholders — `build-preferences.yaml#/budgets.per_pipeline_run = "$<5.00>"`, `business-targets.yaml#/monetization.mode_now = <free-during-demo | live>`. `build_confirm_plan(mode="as-is")` records the **on-disk value**, so a batch confirm-all-`as-is` ledgers the *placeholder string* as a confirmed value — and for the `select` field it isn't even a valid choice (would raise `bad_value` or persist a non-choice). FR-18's `--dry-run` lets a human *notice*, but the spec should **forbid or validate `as-is` over a `<…>`/placeholder value** (skip it → it stays `awaiting`, or reject with guidance). I hit this exact trap building the walk. **Validation:** `test_confirm_all_*` asserts a placeholder-valued field is NOT batch-confirmed as-is.
- **R4-F34** *(A-FR13/FR-13, Interfaces, MEDIUM)* **The new `audience_defaulted` bucket's interaction with the existing `stale` bucket is undefined.** `domain_confirmation` already returns `{confirmable, confirmed, awaiting, stale}` (`stale` = confirmed-but-hand-edited-since). An `audience-default` field the user later hand-edits: is it `stale`, `audience_defaulted`, or **both** (double-counted)? A-FR13 adds the bucket without a precedence rule vs `stale`. **Fix:** define bucket precedence (recommend: an audience-default whose on-disk value diverged is `audience_defaulted` + `stale`-flagged, or promote to a single winning bucket) and assert the buckets **partition** the confirmable set (sum == confirmable, no double-count).
- **R4-F35** *(A-FR6, Data, MEDIUM — concrete edit site)* **The conditional v1→v2 bump requires making `_dump_ledger` schema-aware.** Today `_dump_ledger` writes `schema: LEDGER_SCHEMA` **unconditionally** (`confirmation.py`). A-FR6's "stay `v1` until the first `audience-default` is written" is not free — `_dump_ledger` must emit `v1` unless the map contains an `audience-default` entry, else it. Name this as the exact implementation site in the plan (single writer, so one edit) and test: a ledger with only explicit entries serializes `schema: kickoff.confirmed.v1` byte-for-byte as today.

**Process note (not a suggestion):** the filename is still `PERSONA_EXPERIENCES_*` while the canonical term is `audience` (§0.3) — already tracked as a cosmetic follow-up; noting so a later reviewer doesn't re-raise it.
