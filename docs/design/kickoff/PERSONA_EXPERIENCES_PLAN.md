# Kickoff Persona Experiences — Implementation Plan

**Version:** 1.0 (Post-planning)
**Date:** 2026-07-06
**Requirements:** `PERSONA_EXPERIENCES_REQUIREMENTS.md` (v0.2)

---

## Approach

Persona is a **lens** over the one canonical guided experience — a new dimension **orthogonal** to
`posture`. It resolves to two knobs (DISCLOSURE = prose tier; SURFACE = prompted vs. pre-written).
The build is sequenced so the **persistence spine ships first with zero behavior change**
(Intermediate == today, byte-identical), then each knob is layered behind it.

### New / touched modules

| Module | Change |
|--------|--------|
| `concierge/persona.py` *(new)* | `Persona` enum (`beginner\|intermediate\|advanced`); `resolve_audience_preference` (clone of `guided_routing.resolve_guided_preference`); `apply_audience_defaults` pre-pass; disclosure-tier map. |
| `kickoff_inputs/build_preferences.py` | Add `persona: Optional[str]` to `BuildPreferencesManifest` + validation. |
| `config.py` | Reuse global `preferences.persona` (existing `set_preference`/`get_preference` path, `:299-309`). |
| `kickoff_experience/manifest.py` | Add `AUDIENCE_PROFILES` data + `audience_defaults(persona, cfg)` accessor; `lint_config` coverage for profile value_paths. |
| `concierge/confirmation.py` | Bump `LEDGER_SCHEMA → v2`; add provenance to `ConfirmPlan`/ledger entry; add `audience_defaulted` bucket to `domain_confirmation`. |
| `concierge/confirm_walk.py` | One persona predicate in the `awaiting_fields` comprehension (`:70-73`); advanced prose suppression in `field_prompt_lines` (`:89-108`). |
| `concierge/writes.py` | `load_experience_doc(compact:bool) → tier:str`; new `<!-- PLAIN -->` regions in `KICKOFF_EXPERIENCE_INTRO.md`; update 4 callers. |
| `kickoff_experience/concierge_view.py` | audience block in `build_guided_view` (`:675`) + `guided_parity_digest` (`:719`). **NB path** — this file is under `kickoff_experience/`, not `concierge/`. |
| `cli_concierge.py` | New `kickoff audience [show\|set]` command; `--as-is` batch flag on `kickoff confirm` (FR-12). |
| `test_guided_experience_m4.py` | Update expected parity digests to carry `persona`. |

## Milestones

### M1 — Persistence spine (FR-1, FR-2, FR-3)
`persona.py` resolver + `BuildPreferencesManifest.persona` + global preference + `kickoff audience`
command. Resolver returns **Intermediate** on UNSET; the Intermediate path is today's
`awaiting_fields`/`build_guided_view` with no filter and no pre-pass. **Ships with zero behavior
change** — pure persistence + selection. Guards FR-4 by construction for unset users.

### M2 — Provenance + counting (FR-6, FR-13, OQ-5, OQ-8)
Ledger `v2` with a `audience-default:<slug>` provenance (encoding decided by OQ-8 — leaning additive
`provenance` field for backward tolerance); `domain_confirmation` gains the `audience_defaulted`
bucket; `assess` surfaces it. Pure ledger/reporting — testable in isolation, no UX change yet.

### M3 — Profiles + surface pre-pass (FR-5, FR-7, FR-8, FR-11; needs OQ-9)
`AUDIENCE_PROFILES` in `manifest.py`; `apply_audience_defaults` pre-pass writing shielded defaults via
existing `build_confirm_plan`/`apply_confirm`; persona predicate on `awaiting_fields`. Beginner
reduced-but-written surface goes live. **Blocked on OQ-9** (which fields are shielded — domain- vs
field-granular) before the profile shape is fixed.

### M4 — Disclosure tiers (FR-9, FR-10) — HIGHEST DRIFT RISK
Author `<!-- PLAIN -->` regions **inside** `KICKOFF_EXPERIENCE_INTRO.md`; migrate
`load_experience_doc` to `tier`; wire advanced suppression + beginner plain-language. **Gate on a
single-source review** — the one place NR-1 (no prose fork) can be violated. A separate plain-language
file is prohibited.

### M5 — Efficiency + parity (FR-4, FR-12, FR-14; needs OQ-11)
Advanced confirm-all `--as-is` batch; `persona` block in guided view + parity digest; byte-identity
golden test across personas for a fixed decision script. Update `test_guided_experience_m4.py`.
OQ-11 decides whether web gets a persona *selector* or only *renders* the preference.

## Sequencing rationale

- M1 first so everything downstream has a resolved persona to key on, with **no user-visible change**
  until a knob lands — de-risks the whole feature (can ship M1 and stop).
- M2 before M3 because the pre-pass (M3) must write the provenance the ledger only understands after
  M2 — otherwise audience-defaults masquerade as human confirmations.
- M4 isolated and gated because it is the sole NR-1 (single-source) risk.
- M5 last: parity + byte-identity golden is the acceptance gate proving persona stayed a lens.

## Test strategy

- **Byte-identity golden (FR-4):** a fixed explicit-decision script produces identical `inputs/` +
  `confirmed.yaml` *values* under all three personas.
- **Provenance round-trip (FR-6/FR-13):** audience-default → `domain_confirmation` reports
  `audience_defaulted`; `kickoff confirm <vp>` promotes it to `explicit`.
- **Pre-pass no-override (FR-5):** a field explicitly set before the pre-pass is left untouched.
- **Parity digest (FR-14):** CLI == web == TUI persona rendering (extend existing M4 parity test).
- **Single-source disclosure (FR-9):** loader `tier` projection reads one doc; a lint/test asserts no
  second plain-language file exists.

## Open dependencies (from requirements §5)

- **OQ-8** (ledger provenance encoding) gates M2.
- **OQ-9** (which fields Beginner shields) gates M3 profile shape.
- **OQ-10** (persona-switch re-runs pre-pass?) gates M1/M3 boundary behavior.
- **OQ-11** (web persona selector vs render-only) gates M5 scope.

---

*v1.0 — mapped from requirements v0.2. Five milestones; M1 ships zero-behavior-change persistence,
M4 is the single drift-risk gate. Four open questions block specific milestones.*
