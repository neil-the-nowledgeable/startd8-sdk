# Kickoff Persona Experiences — Implementation Plan

**Version:** 1.3 (Post-CRP R3/R4)
**Date:** 2026-07-06
**Requirements:** `PERSONA_EXPERIENCES_REQUIREMENTS.md` (v0.8)

---

## Approach

Persona is a **lens** over the one canonical guided experience — a new dimension **orthogonal** to
`posture`. It resolves to two knobs (DISCLOSURE = prose tier; SURFACE = prompted vs. pre-written).
The build is sequenced so the **persistence spine ships first with zero behavior change**
(Intermediate == today, byte-identical), then each knob is layered behind it.

### New / touched modules

| Module | Change |
|--------|--------|
| `concierge/audience.py` *(new)* | `KickoffAudience` enum (`beginner\|intermediate\|advanced`); `resolve_audience_preference` (clone of `guided_routing.resolve_guided_preference`); `apply_audience_defaults` pre-pass; disclosure-tier map. *(R1-S2: canonical `audience`, never `persona`.)* |
| `kickoff_inputs/build_preferences.py` | Add `audience: Optional[str]` to `BuildPreferencesManifest` + validation. |
| `config.py` | Reuse global `preferences.audience` (existing `set_preference`/`get_preference` path, `:299-309`). |
| `kickoff_experience/manifest.py` | Add `AUDIENCE_PROFILES` data + `audience_defaults(audience, cfg)` accessor; `lint_config` coverage for profile value_paths. |
| `concierge/confirmation.py` | Bump `LEDGER_SCHEMA → v2`; add provenance to `ConfirmPlan`/ledger entry; add `audience_defaulted` bucket to `domain_confirmation`. |
| `concierge/confirm_walk.py` | One audience predicate in the `awaiting_fields` comprehension (`:70-73`); advanced prose suppression in `field_prompt_lines` (`:89-108`). |
| `concierge/writes.py` | `load_experience_doc(compact:bool) → tier:str`; new `<!-- PLAIN -->` regions in `KICKOFF_EXPERIENCE_INTRO.md`; update 4 callers. |
| `kickoff_experience/concierge_view.py` | audience block in `build_guided_view` (`:675`) + `guided_parity_digest` (`:719`). **NB path** — this file is under `kickoff_experience/`, not `concierge/`. |
| `cli_concierge.py` | New `kickoff audience [show\|set]` command; `--as-is` batch flag on `kickoff confirm` (FR-12). |
| `test_guided_experience_m4.py` | Update expected parity digests to carry `audience`. |

## Milestones

### M1 — Persistence spine (FR-1, FR-2, FR-3; OQ-10 deferred)
`audience.py` resolver + `BuildPreferencesManifest.audience` + global preference + `kickoff audience`
command + the **single canonical `set_audience_preference`** (sole preference writer, called by CLI
and later web). Resolver returns **Intermediate** on UNSET; the Intermediate path is today's
`awaiting_fields`/`build_guided_view` with no filter and no pre-pass. Per **A-OQ10**, `audience set`
writes **only the preference** — no pre-pass. **Ships with zero behavior change** — pure persistence +
selection. Guards FR-4 by construction for unset users.

### M2 — Provenance + counting (FR-6, FR-13, OQ-5, OQ-8)
Ledger `v2` with a `audience-default:<slug>` provenance (encoding decided by OQ-8 — leaning additive
`provenance` field for backward tolerance); `domain_confirmation` gains the `audience_defaulted`
bucket; `assess` surfaces it. Pure ledger/reporting — testable in isolation, no UX change yet.

### M3 — Profiles + surface pre-pass (FR-5, FR-7, FR-8, FR-11; OQ-9 resolved by A-OQ9)
`AUDIENCE_PROFILES` in `manifest.py`; `apply_audience_defaults` pre-pass writing shielded defaults via
existing `build_confirm_plan`/`apply_confirm`; audience predicate on `awaiting_fields`. Per **A-OQ10**
the pre-pass fires at **walk-start** (explicit action), never on a read/render. Shieldability gate per
A-OQ9 (a field is shieldable only if it has a safe reversible default; else always prompted). Beginner
reduced-but-written surface goes live.

### M4 — Disclosure tiers (FR-9, FR-10) — HIGHEST DRIFT RISK
Author `<!-- PLAIN -->` regions **inside** `KICKOFF_EXPERIENCE_INTRO.md`; migrate
`load_experience_doc` to `tier`; wire advanced suppression + beginner plain-language. **Gate on a
single-source review** — the one place NR-1 (no prose fork) can be violated. A separate plain-language
file is prohibited.

### M5 — Efficiency + parity + web selector (FR-4, FR-12, FR-14, FR-19; OQ-11 resolved)
Advanced confirm-all `--as-is` batch (two-phase, A-FR12) + FR-18 dry-run gate; `audience` block in
guided view + parity digest; the byte-identity goldens (A-FR4: inputs-byte + ledger-value +
partial-explicit + pre-pass-then-promote). Update `test_guided_experience_m4.py`. **FR-19 web audience
selector** (OQ-11 = full selector): a CSRF/Origin/session/rate-limit-guarded POST that calls the M1
`set_audience_preference` (NOT a second write path), validates against `KickoffAudience`, writes
preference-only (pre-pass still at walk-start per A-OQ10). **M5 carries an explicit security-review
gate for FR-19** (riskiest surface; consult `--serve` precedent).

## Sequencing rationale

- M1 first so everything downstream has a resolved audience to key on, with **no user-visible change**
  until a knob lands — de-risks the whole feature (can ship M1 and stop).
- M2 before M3 because the pre-pass (M3) must write the provenance the ledger only understands after
  M2 — otherwise audience-defaults masquerade as human confirmations.
- M4 isolated and gated because it is the sole NR-1 (single-source) risk.
- M5 last: parity + byte-identity golden is the acceptance gate proving audience stayed a lens.

## Test strategy

- **Byte-identity golden (FR-4):** a fixed explicit-decision script produces identical `inputs/` +
  `confirmed.yaml` *values* under all three audiences.
- **Provenance round-trip (FR-6/FR-13):** audience-default → `domain_confirmation` reports
  `audience_defaulted`; `kickoff confirm <vp>` promotes it to `explicit`.
- **Pre-pass no-override (FR-5):** a field explicitly set before the pre-pass is left untouched.
- **Parity digest (FR-14):** CLI == web == TUI audience rendering (extend existing M4 parity test).
- **Single-source disclosure (FR-9):** loader `tier` projection reads one doc; a lint/test asserts no
  second plain-language file exists.

## Open dependencies (from requirements §5) — ALL RESOLVED

- **OQ-8** → additive `provenance` field + conditional bump (A-FR6). M2 unblocked.
- **OQ-9** → shieldability criterion / safe-reversible-default gate (A-OQ9). M3 unblocked.
- **OQ-10** → DEFERRED: `set` = preference-only; pre-pass at walk-start (A-OQ10). M1/M3 boundary fixed.
- **OQ-11** → FULL web selector via the canonical setter + guards + M5 security gate (A-FR19). M5 scope fixed.

*No open questions remain — the design is decision-complete and ready for implementation (start M1).*

---

## Post-CRP Amendments (v1.1)

> Triaged R1/R2 (Appendix C). Re-keyed to **requirements v0.6**. All accepted; dispositions in Appendix A.

- **Milestone remap (R1-S1)** — the four panel FRs are now placed:
  - **FR-15** (beginner reassurance moment) → **M4** (needs plain-language wording).
  - **FR-16** (in-session expand-surface escape hatch, mechanics per A-FR16) → **M3** (owns the pre-pass it reverses).
  - **FR-17** (live in-walk provenance, parity-bound per A-FR17) → **M2 → M3 boundary** (data in M2, rendered in M3 walk).
  - **FR-18** (confirm-all `--dry-run`/preview, mandatory) → **M5 gate on FR-12** (two-phase collect-then-apply, A-FR12).
- **M2 hardened (R1-S4, R2-S20, A-FR6)** — conditional `v1→v2` bump (only on first audience-default write); provenance-absence ⇒ explicit; add v1-ledger-load fixture + rollback tolerance; add **`test_assess_no_audience_regression`** as an **M2 merge gate** (A-FR13).
- **M3 hardened (R2-S21, A-FR16)** — pre-pass idempotency test (2nd run writes nothing, no `at` bump); encode the un-shield/no-re-shield + broaden-audience-re-opens contract.
- **M4 hardened (R1-S6, R2-S22, A-FR9)** — replace the manual single-source review with an **automated per-region tier-resolution + `expanded ⊇ light` superset lint**; co-located tier variants, not append-only regions.
- **Test strategy additions (R1-S3)** — `test_confirm_all_equals_single`; FR-4 value-only normalization + partial-explicit golden + pre-pass-then-promote golden; v1-ledger fixture.

*v1.1 — re-keyed to requirements v0.6; FR-15/16/17/18 mapped; M2/M3/M4 hardened per CRP; module table
canonicalized to `audience`. M1 still ships zero-behavior-change persistence; M4 remains the single
drift-risk gate (now automated).*

## Post-CRP Amendments — R3/R4 (v1.3)

> Triaged R3/R4 (requirements Appendix C, `claude-opus-4-8` — R4 builder's-eye, verified vs `origin/main`
> post-#115/#116/#117). All accepted; requirements §3.2. These land at specific milestones/edit-sites:

- **M2 — `_dump_ledger` schema-aware (A-FR6d, R4-F35)**: emit `schema: v1` unless the map holds an
  `audience-default` entry; test all-explicit ledger serializes `v1` byte-for-byte. **+ bucket partition
  (A-FR13b, R4-F34)**: `domain_confirmation` buckets MUST partition the confirmable set (Σ==confirmable);
  an audience-default that diverged on disk is `audience_defaulted`+`stale`-flagged, not double-counted.
- **M3 — pre-pass fail-closed vs the present-file gate (A-FR11b, R4-F32, HIGH)**: `kickoff instantiate`
  is a documented precondition; walk-start on an un-instantiated project instantiates-then-shields or
  refuses — **never silently full-surfaces**. FR-11 golden includes an un-instantiated start. **+
  provenance write-path invariant (A-FR6c, R3-F31)**: `apply_audience_defaults` never writes a
  `provenance`-less entry; add `test_prepass_writes_are_provenance_tagged` + a no-untagged-writer grep.
- **M4 — tier loader composes with post-#115 code (A-FR9b, R3-F30, HIGH)**: `tier` is orthogonal to the
  existing `section=` axis; register tier/`<!-- PLAIN -->` markers in `_SLICE_MARKERS` (else Beginner
  prose leaks into `explain`); **replace** the silent full-doc fallback with fail-closed degrade-to-light.
  The M4 gate now also asserts no tier marker survives a full/`explain` render.
- **M5 — no `as-is` over placeholders (A-FR12b, R4-F33, HIGH)**: confirm-all skips/rejects a field whose
  on-disk value matches a `<…>`/placeholder pattern (stays `awaiting`); `test_confirm_all_*` asserts it.

*v1.3 — re-keyed to requirements v0.8; R3/R4 (incl. two builder's-eye HIGH integration bugs vs same-day
merges #115/#116) mapped to M2–M5. M1 unchanged.*

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
| R1-S1 | FR-15/16/17/18 unmapped; plan keyed to v0.2 | opus | Post-CRP §: mapped to M4/M3/M2→M3/M5; re-keyed v0.6 | 2026-07-06 |
| R1-S2 | Module table used reserved `persona` | opus | Renamed to `audience.py`/`KickoffAudience`; `build_preferences.audience`→`audience` | 2026-07-06 |
| R1-S3 | Missing mandated tests + FR-4 normalization | opus | Added to Test strategy additions | 2026-07-06 |
| R1-S4, R2-S20 | M2 backward-compat unspecified | opus+sonnet | M2 hardened: conditional bump, v1 fixture, rollback | 2026-07-06 |
| R1-S5 | M3/M4 sequencing strands Beginner in jargon | opus | FR-15 wording sequenced with M4 | 2026-07-06 |
| R1-S6, R2-S22 | M4 single-source gate manual/insufficient | opus+sonnet | M4 hardened: automated superset lint | 2026-07-06 |
| R2-S21 | No pre-pass idempotency test | sonnet | M3 hardened: 2nd-run-no-write test | 2026-07-06 |
| R2-S23 | Byte-identity golden misses pre-pass-then-promote | sonnet | Added pre-pass-then-promote golden to M5 | 2026-07-06 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — general-purpose (opus) — 2026-07-06

- **R1-S1** *(Milestones/footer, Architecture, critical)* Plan is keyed to requirements **v0.2**; the four panel FRs (15–18, added v0.4) are unmapped: no milestone builds FR-15/16/17, and M5 mentions confirm-all but not FR-18's MANDATORY `--dry-run`. Fold FR-15/16 into M3, FR-17 into the M2→M3 boundary, make FR-18 an explicit M5 gate on FR-12; bump the version reference to v0.5.
- **R1-S2** *(module table, Architecture, high)* Table specifies `concierge/persona.py (new)` + `Persona` enum — mixing the RESERVED `persona` token with `audience`. Rename module/enum/symbols to canonical `audience` (`audience.py`, `KickoffAudience`, `resolve_audience`); only the doc filename keeps "Persona".
- **R1-S3** *(Test strategy, Validation, high)* Missing FR-12's `test_confirm_all_equals_single`, FR-4's value-only normalization + partial-explicit golden, and a v1-ledger-load fixture (OQ-8).
- **R1-S4** *(M2, Data, high)* State the provenance-absence invariant: absence of `provenance` ⇒ explicit/human, so v1 ledgers + pre-existing entries route to `confirmed`, never `audience_defaulted` (this is what preserves FR-13 non-regression). Add the conditional-bump rule (R1-F1) to M2 acceptance.
- **R1-S5** *(M3/M4, Risks, high)* M3 ships Beginner reduced surface while M4 (plain-language) lands later → interim Beginner gets reduced surface in Intermediate-level jargon; FR-15 reassurance would be non-plain. Sequence FR-15 wording with M4 or state "M3 interim = reduced surface, light prose." M3 pre-pass must encode the R1-F4 idempotency/un-shield contract.
- **R1-S6** *(M4, Architecture, medium)* M4's NR-1 protection is a MANUAL review + file-count lint — neither proves the projection is well-formed. Make the merge gate the automated per-region tier-resolution lint (R1-F3).

#### Review Round R2 — claude-sonnet-4-6 (adversarial) — 2026-07-06

- **R2-S20** *(M2, Data, critical)* Ships the v1→v2 bump with no backward-compat test. Add a v1 `confirmed.yaml` fixture; assert v2 code loads it with identical counts + no error; address rollback (v1 code vs v2 file).
- **R2-S21** *(M3, Validation, high)* No idempotency test for `apply_audience_defaults` under the OQ-10 re-run/switch path. Add: run pre-pass twice → second run writes nothing and does NOT bump existing `at` timestamps.
- **R2-S22** *(M4, Architecture, high)* File-count lint won't catch a `<!-- PLAIN -->` region that drifted from its "light" prose. Add a golden asserting `tier=expanded` ⊇ `tier=light`, or a checksum-of-adjacent-light-prose lint.
- **R2-S23** *(M5, Validation, high)* `test_audience_byte_identity` as a fresh-start script misses the pre-pass-then-promote timeline (the one that produces `at`/provenance divergence). Mandate a "pre-pass first → promote all → compare vs Intermediate-direct" fixture in the M5 gate.

## Requirements Coverage Matrix — R1

| FR | Plan milestone(s) | Coverage |
|----|-------------------|----------|
| FR-1/2/3 | M1 | Covered (FR-2 has schema-bump tension — R1-F1) |
| FR-4 | M5 | Covered but NARROW (R1-F2/R2-F21) |
| FR-5 | M3 | Covered |
| FR-6 | M2 | Covered (conditional bump + backward-compat — R1-F1/R2-F25) |
| FR-7/8 | M3 | Covered (extend lint per R1-F5) |
| FR-9/10 | M4 | Covered but UNDER-SPECIFIED (R1-F3/R2-F23) |
| FR-11 | M3 | Covered (idempotency gap — R1-F4) |
| FR-12 | M5 | Covered; `test_confirm_all_equals_single` missing from plan (R1-S3); "reuses"→"extends" (R2-F28) |
| FR-13 | M2 | Covered; non-regression test missing (R2-F26) |
| FR-14 | M5 | Covered; `persona`→`audience` key (R2-F27) |
| **FR-15** | **none → map to M3/M4** | **GAP (R1-S1)** |
| **FR-16** | **none → map to M3** | **GAP (R1-S1) + mechanics undefined (R2-F24)** |
| **FR-17** | **none → map to M2→M3** | **GAP (R1-S1) + parity binding (R1-F6)** |
| **FR-18** | M5 (partial) | **PARTIAL — dry-run/preview not a gate (R1-S1)** |

No orphan plan steps. All gaps are one-directional (v0.4 panel FRs unmapped because the plan is still keyed to v0.2).
