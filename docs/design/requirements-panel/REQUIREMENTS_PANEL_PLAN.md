# Requirements Panel — Implementation Plan

**Version:** 0.2 (Post-CRP — R1+R2 triage integrated)
**Date:** 2026-07-02
**Requirements:** `REQUIREMENTS_PANEL_REQUIREMENTS.md` (v0.4)
**Branch:** `feat/requirements-panel-spec` (design-only; code lands on a later `feat/requirements-panel`).

---

## Planning discoveries (fed the reflection pass)

| What v0.1 assumed | What planning (live-code read) revealed | Impact |
|-------------------|-----------------------------------------|--------|
| `grounding_guard.unsupported_specifics` grounds against the project brief | `grounding_guard.py:81-89` — `_brief_corpus` is `goals+constraints+known_positions+display_name` of **the persona's own brief**. It grounds a persona's answer against *that persona's* stated positions, not the project. | **FR-RP-4 owns `ground_requirement`** with a **project corpus** (problem-statement brief + schema entity/field names), reusing only the guard's `extract_money`/`extract_percent` (publicly exported at `grounding_guard.py:68-69`) + a temporal extractor. |
| A drafted requirement, being an estimate, should suppress the specifics check like values do | `recommend.py:130-133` — comment: *"Do NOT carry the reactive unsupported-specifics flags — an estimate is expected to introduce a value the brief never stated."* Only `check_contradiction` runs on value drafts. | **Requirements invert this**: a fabricated `"40% faster"` **is** the failure. FR-RP-4 **runs** the specifics check; the estimate-suppression rationale does not apply to intent prose. |
| Approve reuses the `manifest` proposal kind (Manifest-Suggester template) | No requirements shape in `kickoff_experience/proposals.py:PROPOSAL_KINDS`; requirements are markdown in `docs/design/`, not a `CONVENTION_PATHS`-mapped manifest. | **FR-RP-6 apply = CLI markdown file-write** at human privilege; **CRP is the second gate**. No `PROPOSAL_KINDS` change (NR-RP-3). |
| `input_domains.py` is the "what to draft" layer to reuse; `resolve_owner`/`route` reusable as-is | `input_domains.py:79-101,208-248` models **scalar YAML `FieldSlot`s**; requirements units are prose sections/FR-classes. **CRP R1-S1/R1-F1 + R2-S1 falsified the reuse twice:** `resolve_owner:308-325` calls `get_domain()` → `None` off the 3 value domains, and `recommend._default_domains:162-168` enumerates by `rel_path().is_file()` → **zero** requirements domains. | **FR-RP-1 owns `RequirementDomain`**; **`route()` IS reusable** (keys on a symbol string) but **owner-resolution AND domain-enumeration are OWNED** — a verbatim "mirror `recommend_inputs`" would draft nothing. |
| Personas draft, then each draft is applied one at a time | The Manifest-Suggester's just-triaged **R2-S1** proved a per-item apply against a shared artifact clobbers prior entries. A requirements doc has the same property. | **FR-RP-3 owns a synthesis pass** that assembles the whole doc once; approve writes the assembled doc, not N incremental splices. |

**Net:** the loop killed the "reuse the guard + reuse an apply kind" shortcuts (both architecturally
wrong on inspection) and sharpened the capability to **owning** a project-grounding guard, a
`RequirementDomain` descriptor, a synthesis pass, and a file-write+CRP apply — while genuinely reusing
persona/routing/roster/store/`panel.ask`/telemetry.

---

## Approach & step map

### Step 1 — The requirements-domain model + `$0` baseline (FR-RP-1)
- New `src/startd8/requirements_panel/` package. `domains.py`:
  - `RequirementDomain{area, owning_role, prompt_template, grounds_on: {brief, schema}}` — the
    section/FR-class → owning-role map (structural analogue of `input_domains.DomainSpec`).
  - A default registry: `problem`, `data` (entity-touching FRs), `ux`, `ops`, `security`, `compliance`.
  - **Owned enumerator** `requirement_domains() -> list[RequirementDomain]` — returns the in-code
    registry; do **NOT** call `recommend._default_domains` (file-driven → zero domains, R2-S1).
- `baseline.py`: `scaffold(brief, schema_text) -> RequirementDoc` — deterministic (`$0`) Problem gap
  table + one entity-touching FR **stub per primary entity**, where **"primary entity" = a parsed
  `PrismaModel` excluding compound-`@@id` join tables via `PrismaModel.compound_unique_keys()**`
  (`prisma_parser.py:100-111`, R2-F5). Standard `## Non-Requirements` / `## Open Questions` headings;
  unfilled areas marked `<needs-owner>`. **No LLM.**

### Step 2 — Project-grounding guard (FR-RP-4, owned — NOT the panel's)
- `grounding.py`: `ground_requirement(candidate, project_corpus, schema) -> Ok|Flag(reasons)`.
  - `project_corpus` = brief text + declared entity/field names.
  - Reuse `grounding_guard.extract_money`/`extract_percent` (the only public extractors). **Own
    `extract_temporal`, which MUST port the private `_MONTH_DATE` bare-month exclusion + day-adjacency**
    (R2-S2 — the guard's conservative behavior is private, not reused, so replicate it or the cited
    prose-safety property is unfounded).
  - **Two severities (R2-F2 / R1-S3 Ask 2):** a **schema entity/field absence** = **deterministic, high**
    flag; **money/percent/explicit-date** unsupported specifics = **advisory**; a **bare year** (`_YEAR`
    matches every `19xx`/`20xx`, floods prose) = **advisory-low** or suppressed by priming the corpus
    with brief/schema temporal tokens.
  - **"Soften" (R1-F2):** candidate **text byte-unchanged**; only a **`flags` list** is populated (no
    `check_grounding` enum-hedge — a `RequirementCandidate` has no self-reported `Grounding` enum).

### Step 3 — Role-informed drafting (FR-RP-2) — reuse-vs-own (R2-S1)
- `elicit.py`: `async elicit_requirements(package_root, panel, brief, schema, *, domains=None, cap=None,
  session_id=None) -> ElicitationRun`. **Reuse-vs-own is explicit — do NOT verbatim-mirror
  `recommend_inputs`:**

  | Reuse as-is | Own (value-domain-bound in the panel) |
  |-------------|----------------------------------------|
  | `panel.ask` · `panel.preflight_budget` · `telemetry.span` · `routing.route(briefs, area)` | domain **enumeration** (`_default_domains` is file-driven) · **owner resolution** (`resolve_owner` → `None` off value domains) · **grounding** (Step 2) |

  Flow: `requirement_domains()` → `route(briefs, area)` + owned bounded resolver (default `owning_role`
  → high-confidence `answers_for` → skip) → budget-preflight the resolved+capped set → `await
  panel.ask(owner, drafting_prompt, value_path=area)` → skip `UNAVAILABLE`/`DEFERRED` (never fabricate)
  → Step 2 grounding → stage `RequirementCandidate`s (per-FR provenance, Step 5/R2-S3). Prompt carries
  **brief + literal declared entity names**. Parent span `requirements.elicit_pass`. Paid; the `$0`
  baseline runs without it.

### Step 4 — Sanitization (FR-RP-7, before synthesis)
- `sanitize.py`: `neutralize_headings(text) -> text | Reject` — scan every candidate free-text field for
  **`^#{1,6}\s` (h1–h6) AND setext underlines** (`^=+$` / `^-+$` under a text line) — the original
  `#{2,4}` missed h1/h5/h6 + setext (R1-F5). **Neutralize primitive = blockquote-demotion** (`> ## x`),
  safe for `^`-anchored CRP `####` parsing; a **surviving un-demoted line-start heading** is what the
  readiness gate (Step 6.5) fails on (R2-S5 reconciles neutralize-vs-gate). (Manifest-Suggester R3-S1.)

### Step 5 — Synthesis pass (FR-RP-3, owned, **fully `$0`/deterministic** — R1-S6)
- `synthesis.py`: `synthesize(baseline, candidates) -> RequirementDoc` — **no LLM**. (a) **dedupe by
  normalized-slug equality**; near-but-not-equal normalizations are **kept as distinct** (or lifted to an
  Open Question), never merged → dedupe can never silently drop a distinct FR (R1-F3). (b) **stable
  `FR-<AREA>-<n>` IDs persisted in the store / content-hash-derived, NOT re-ordinal-assigned** — a
  re-elicit must not renumber (CRP anchors on FR-IDs, R1-F4). (c) order by area. (d) **lift cross-role
  conflicts verbatim** into `## Open Questions` from the already-sanitized+grounded candidate text —
  generating **no new LLM prose** (so nothing bypasses Step 4/Step 2 — this satisfies R2-S6 by
  construction). Emits the **whole** doc (R2-S1 discipline).

### Step 6 — review → approve loop + store (FR-RP-8, mirror the panel)
- `store.py` stages the run out-of-band — **mirror `ProposalStore`'s shape** (atomic `mkstemp`+`os.replace`,
  `sort_keys`+`indent=2`, session GC, `_safe_session_component` traversal guard). CLI
  `cli_requirements.py` (`startd8 requirements`): `elicit` · `synthesize` · `review` (`$0` render of the
  **literal** doc bytes that approve would write, Manifest-Suggester R3-S2; **advisory grounding flags
  surfaced out-of-band, not in the bytes** — R2-F4) · `approve`/`reject`.
- **Lifecycle (R2-S4):** once a versioned `*_REQUIREMENTS.md` exists (prior approve, or CRP/human edits),
  `elicit`/`approve` **refuse permanently** with an edit-in-place pointer — never regenerate over a
  CRP/human-owned doc.

### Step 6.5 — Pre-CRP readiness gate (FR-RP-6, R1-S2 — **blocking, `$0`, deterministic**)
- Between `approve` and the file-write, a `$0` gate **blocks** (never auto-approves) when: any
  non-`<needs-owner>` candidate carries an unresolved grounding flag on a `MUST`/`SHALL` (the P1 boundary
  invariant); any `<needs-owner>` stub was promoted; or a **surviving line-start `^#{1,6}`/setext heading**
  remains (a blockquote-demoted `> ## x` **passes**, R2-S5). Resolves **OQ-RP-8** toward a blocking gate,
  breaking the FR-RP-6/P6 circularity. `apply.py` then writes the markdown **atomically / `O_EXCL`** so a
  concurrent create cannot be clobbered (R1-S3, TOCTOU).

### Step 7 — CRP hand-off + reflective-loop discoverability (FR-RP-6/9)
- `approve` emits the ready-to-run `/new-cnvrg-rvw-prmpt --plan … --requirements …` invocation (dual-doc)
  and a one-line pointer from the `reflective-requirements` entry point / Concierge "no reqs doc" gap.

### Step 8 — Tests
- `$0` baseline: brief+schema → a stub per **primary entity**; a 2-domain + 1 compound-`@@id` join-model
  schema yields stubs for the **2 domain models only** (R2-F5); no invented intent (all `<needs-owner>`),
  **no LLM call**.
- Owner-resolution (R1-S1/R1-S4a): `input_domains.resolve_owner("security", briefs) is None` (proves
  non-reuse); the **owned** resolver returns the owning role for a requirements roster; un-owned area →
  skip, never a loose match. Assert no code path calls `recommend._default_domains` (R2-S1).
- Grounding: an FR naming a non-existent entity is a **high** flag; `"$2M ARR"` unsupported → advisory;
  `"deliver by 2027"` (brief silent) → **advisory-low**, never high (R2-F2); `"may improve latency"` →
  **no** temporal flag, `"March 2027"` → flag (R2-S2/R2-F1); a flagged candidate's **text is byte-unchanged**
  (R1-F2).
- Panel reuse: `elicit_requirements` goes through `panel.ask` (cost/transcript/span recorded), never a
  bare `Persona`.
- Provenance (R2-S3/R2-F3): `is_estimate(baseline_stub)` is **False**; a synthesized doc round-trips
  three distinguishable **per-FR** markers (`baseline`/`estimate`/`human`).
- Sanitization: `# x`, `###### x`, and a setext `Title\n---` in a persona field are all neutralized
  (R1-F5); a `> ## x` blockquote **passes** the readiness gate, a bare `^## x` **fails** (R2-S5).
- Synthesis (`$0`): two roles' identical FRs → one entry; two **distinct** similar-normalizing FRs → both
  survive (or → OQ), never merged (R1-F3); re-synthesize with one added candidate → pre-existing FR IDs
  unchanged (R1-F4); `synthesize` makes **no LLM call** (R1-S6); a synthesis-emitted OQ contains no
  un-sanitized heading (R2-S6).
- Readiness gate (R1-S2/R1-S4c): a run with an ungrounded `$2M ARR` **intent** FR refuses `approve` until
  resolved.
- Apply + lifecycle: approve writes atomically (`O_EXCL`); a pre-existing target → refuse byte-unchanged,
  concurrent-create race → no clobber (R1-S3); `elicit` against an existing v0.2 doc → permanent
  edit-in-place refuse (R2-S4).
- Discoverability (R1-S4b): the FR-RP-9 pointer is emitted from the reflective-loop / Concierge "no reqs
  doc" gap.

---

## §7 Validation Strategy
- **Bucket boundary (P1):** every candidate + **every FR** in the synthesized doc carries a **per-FR**
  provenance marker (`baseline`/`estimate`/`human`); approve requires an explicit human action and passes
  the readiness gate (no auto-approve path exists); a `MUST`/`SHALL` neither grounded nor `<needs-owner>`
  blocks approve (the P1 boundary invariant).
- **Dual grounding (P3), two severities:** a schema-absence is a **high/deterministic** flag; unsupported
  money/percent/date is **advisory**; bare-year is **advisory-low**; a doubly-supported specific passes;
  flagging never mutates candidate text.
- **No-silent-overwrite (R2-S1) + `$0` synthesis (R1-S6):** synthesizing N role contributions yields all
  N; distinct similar FRs are never merged; `synthesize` makes no LLM call.
- **Sanitization (R3-S1/R1-S5):** injected `^#{1,6}`/setext lines never survive un-demoted into the
  assembled doc or the CRP appendix scaffold; a demoted `> ## x` passes the readiness gate.
- **Reuse-not-fork:** `elicit_requirements` imports `panel`/`routing`/`ProposalStore` but adds no value
  domain and no proposal kind; **no path calls `recommend._default_domains`/`input_domains.resolve_owner`**
  for requirements; `PROPOSAL_KINDS` unchanged.
- **Panel-isolation (NR-RP-1):** the stakeholder-panel value pass is untouched.

## Risks
- **R1 — Grounding false-positives on prose.** The specifics extractors were tuned for scalar value
  answers; requirement prose is longer and cites years/percents freely. Mitigation: advisory severities
  (bare-year → advisory-low, R2-F2) + CRP as authoritative gate; the owned `extract_temporal` **ports**
  the guard's private bare-month exclusion (R2-S2) rather than merely citing it (`grounding_guard.py:39-46`
  is private and not reused).
- **R2 — Synthesis is `$0`/deterministic (R1-S6).** Synthesis makes **no LLM call**: dedupe/ID/order are
  mechanical and cross-role conflicts are **lifted verbatim** into Open Questions (no generated prose).
  This removes the earlier "hard LLM step" framing and the R2-S6 leak (nothing enters the doc after the
  Step-4 sanitize / Step-2 ground). *If a future increment makes conflict-framing spend, Steps 4/2 must
  re-run on synthesis output — re-opening R2-S6.*
- **R3 — Scope creep past bucket-4.** Mitigation: P1 scope lock + **per-FR** provenance + human-approve-only
  + the blocking readiness gate (MUST/SHALL grounding) + CRP second gate.
- **R4 — Roster coupling.** Mitigation: reuse `persona`/`routing`/`roster` only (generic); ship a
  default requirements roster (OQ-RP-7) keyed on FR-area `answers_for`, no new roster grammar.
- **R5 — Target-file clobber / TOCTOU (R1-S3).** A check-then-write race could overwrite an existing
  `*_REQUIREMENTS.md`. Mitigation: atomic `O_EXCL` write; stale-session detection (target exists /
  content-hash mismatch).
- **R6 — Post-CRP re-elicit (R2-S4).** A later `elicit`/`approve` must not regenerate over a CRP/human-owned
  doc. Mitigation: one-shot lifecycle — once a versioned doc exists, refuse permanently with an
  edit-in-place pointer.

---

## Requirements Coverage (self-check, post-CRP v0.2)

| Requirement | Plan Step(s) | Coverage | Post-CRP note |
|-------------|-------------|----------|---------------|
| FR-RP-1 (`$0` baseline) | Step 1 | Full | "primary entity" now deterministic via `compound_unique_keys()` (R2-F5). |
| FR-RP-2 (role drafting via `panel.ask`) | Step 3 | Full | Owner-resolution + enumeration **owned** (reuse-vs-own table); `route()` reused (R1-S1/R2-S1). |
| FR-RP-3 (synthesis, no overwrite) | Step 5 | Full | Fully `$0`; keep-both dedupe + hash-stable FR-IDs (R1-F3/R1-F4/R1-S6). |
| FR-RP-4 (project-grounding guard) | Step 2 | Full | Owned `extract_temporal` ports bare-month exclusion; two severities; "soften"=flags-only (R2-S2/R2-F2/R1-F2). |
| FR-RP-5 (provenance) | Steps 3, 5 | Full | **Per-FR** + distinct `$0`-baseline constant (R2-S3/R2-F3). |
| FR-RP-6 (readiness-gated write + CRP + lifecycle) | Steps 6, 6.5, 7 | Full | Blocking readiness gate + atomic write + one-shot lifecycle (R1-S2/R1-S3/R2-S4). |
| FR-RP-7 (heading sanitization) | Step 4 | Full | `^#{1,6}`+setext; blockquote-demotion reconciled with the gate (R1-F5/R2-S5). |
| FR-RP-8 (loop + surface) | Steps 6, 6.5 | Full | `review` surfaces flags out-of-band (R2-F4). |
| FR-RP-9 (discoverable from reflective loop) | Step 7 | Full | Now validated (R1-S4b). |

---

*v0.2 — Post-CRP (R1 breadth + R2 adversarial, `claude-opus-4-8-1m`; all 12 S-suggestions accepted).
Integrated: the "mirror `recommend_inputs`" claim corrected (own enumeration **and** owner-resolution;
`route()` reused) — Step 3 now a reuse-vs-own table (R1-S1/R2-S1); Step 2 owns `extract_temporal`
(ports the private bare-month exclusion) with two grounding severities (R2-S2); synthesis declared
fully `$0`/deterministic → R2-S6 satisfied by construction (R1-S6); new Step 6.5 blocking readiness
gate + atomic `O_EXCL` write (R1-S2/R1-S3); one-shot post-CRP lifecycle refuse (R2-S4); Step 4 scan
broadened to `^#{1,6}`+setext with blockquote-demotion reconciled against the gate (R1-F5/R2-S5); Step 1
"primary entity" via `compound_unique_keys()` (R2-F5); per-FR provenance + distinct baseline constant
(R2-S3); Risks R5/R6 added; §7 + Step-8 tests expanded. Matches the requirements v0.4 and the Appendix
A triage notes.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to
Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or
Appendix B (rejected with rationale). **Do not delete A/B** — cross-model memory.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items
  already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest
  existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: list agreements in an **Endorsements** section.
- **When validating (orchestrator)**: append a row to Appendix A (applied) or Appendix B (rejected).
- **If rejecting**: record **why** (specific rationale).

### Areas Substantially Addressed (>= 3 accepted)

- **Validation**: 4 accepted (R1-S2, R1-S4, R1-S5, R2-S5)

### Areas Needing Further Review (below threshold of 3)

- **Interfaces**: 2/3 accepted (R1-S1, R2-S1)
- **Risks**: 2/3 accepted (R1-S3, R2-S4)
- **Data**: 2/3 accepted (R2-S2, R2-S3)
- **Architecture**: 1/3 accepted (R1-S6)
- **Ops**: 1/3 accepted (R2-S6)
- **Security**: 0/3 accepted (covered on the requirements side; R1-F5/R2-S5 heading-injection)

> Triage disposition: **all 12 R1+R2 S-suggestions ACCEPTED**; Appendix B empty. Bodies not yet
> rewritten — these notes are the v0.4 delta. Two cross-item reconciliations resolved at triage:
> **R1-S6 → synthesis is fully deterministic `$0`** (conflict-framing lifts existing sanitized+grounded
> candidate text into an Open Question, generating no new LLM prose), which makes **R2-S6 satisfied by
> construction**; and **R1-S2 ↔ R1-F5** reconciled via **R2-S5** (blockquote-demotion is the neutralize
> primitive; the readiness gate fails only on a surviving line-start `^#{1,6}`/setext heading).

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-S1 | `resolve_owner` is **not** reusable — own a `RequirementDomain`-aware owner resolver; fix "reusable as-is" + the `routing.route` co-location error | claude-opus-4-8-1m (R1) | ACCEPT — **high, blocking**. Verified `input_domains.resolve_owner:308-325` calls `get_domain()` → returns `None` for any non-value-domain name (would skip every requirements area). v0.4: correct Planning-discoveries row 4 + Step 3; add `resolve_owner` to §Reference-Audit marked **not reusable**; own `resolve_requirement_owner`. Test: `resolve_owner("security", briefs) is None`. | 2026-07-02 |
| R2-S1 | The "mirror `recommend_inputs`" claim fails a **second** time — `_default_domains` is YAML-file-driven; own the enumerator too. Replace with an explicit reuse-vs-own table | claude-opus-4-8-1m (R2) | ACCEPT — **high**. Verified `recommend.py:162-168` gates on `rel_path().is_file()`; requirements domains are an in-code registry with no YAML → verbatim mirror enumerates zero. v0.4: Step 3 gets a **Reuse** (`panel.ask`/`preflight_budget`/`telemetry.span`/`routing.route`) vs **Own** (enumeration + owner-resolution + grounding) table. Test: no path calls `recommend._default_domains`. | 2026-07-02 |
| R1-S3 | Define stale-session detection **and** make existence-check + write atomic (`O_EXCL`), not check-then-`os.replace` (TOCTOU) | claude-opus-4-8-1m (R1) | ACCEPT — **high**. `ProposalStore`'s atomic staging doesn't protect the target `*_REQUIREMENTS.md`. v0.4: Step 6 + new Risk R5. Test: pre-existing target → refuse byte-unchanged; concurrent-create race → no clobber. Pairs with R2-S4 (the lifecycle half). | 2026-07-02 |
| R2-S4 | Add a post-CRP re-elicit **lifecycle**: once a versioned doc exists, `elicit`/`approve` **refuse permanently** and point to edit-in-place | claude-opus-4-8-1m (R2) | ACCEPT — **high**. R1-S3 fixes the race; this fixes the lifecycle. The doc's purpose is to evolve via CRP/human → re-elicit must never regenerate over it. v0.4: Step 6 clause + new Risk R6. Test: `elicit` against a v0.2 doc refuses with an edit-in-place pointer, no bytes change. | 2026-07-02 |
| R1-S2 | Add Step 6.5 — a **`$0` deterministic pre-CRP readiness gate** that blocks (never auto-approves) `approve` on unresolved grounding flags on MUST/SHALL, promoted `<needs-owner>` stubs, or surviving injected headings | claude-opus-4-8-1m (R1) | ACCEPT — **high**. Breaks the FR-RP-6/P6 circularity (focus ask 4) with a deterministic gate, resolving **OQ-RP-8 toward a blocking readiness gate** (not merely an advisory score). Gate criterion refined by R2-S5 (line-start heading survives ⇒ fail). Test: an ungrounded `$2M ARR` intent FR refuses approve until resolved. | 2026-07-02 |
| R2-S2 | The owned `extract_temporal` must **port** the guard's private `_MONTH_DATE` bare-month exclusion + day-adjacency, or strike the Risk-R1 mitigation clause citing `grounding_guard.py:39-46` | claude-opus-4-8-1m (R2) | ACCEPT — **high**. Verified `_temporal`/`_MONTH_DATE` are private (`__all__` at :26-31 exports only money/percent). The cited prose-safety property is unfounded unless replicated. v0.4: Step 2 states the port; ties requirements R2-F1. Test: bare month verb → no flag; "March 2027" → flag. | 2026-07-02 |
| R1-S6 | Reconcile the synthesis determinism boundary — CLI Step 6 says `synthesize` `$0`, Risk R2 calls it "the hard LLM step" | claude-opus-4-8-1m (R1) | ACCEPT — **medium**, **resolved toward fully `$0`/deterministic synthesis**: dedupe/ID/order **and** conflict-lifting are mechanical (a conflict lifts the two candidates' already-sanitized+grounded text verbatim into an Open Question; no new LLM prose). v0.4: rewrite Risk R2 to drop the "hard LLM step" framing; FR-RP-3/Step 5 state synthesis spends `$0`. This resolution makes **R2-S6 moot by construction**. Test: `synthesize` makes no LLM call. | 2026-07-02 |
| R2-S6 | If synthesis conflict-framing spends, run sanitize+ground **on synthesis output** (Step 4 currently precedes Step 5) | claude-opus-4-8-1m (R2) | ACCEPT — **medium**, **satisfied by the R1-S6 resolution**. Because synthesis is now fully `$0` and emits only already-sanitized+grounded candidate text (no post-synthesis LLM prose), nothing bypasses Step 4/Step 2. v0.4: add a §7 assertion that synthesis introduces no un-sanitized text (guards the invariant even if a future increment makes conflict-framing spend — at which point this re-opens). | 2026-07-02 |
| R2-S3 | Specify (a) a **distinct** `$0`-baseline provenance value (not `ESTIMATE_PROVENANCE`) and (b) a **per-FR** provenance carrier on `RequirementDoc` | claude-opus-4-8-1m (R2) | ACCEPT — **medium/high**. Verified `is_estimate` requires `origin.startswith("panel:")` (`recommend_provenance.py:44-46`); a no-LLM baseline stub has no persona origin. Extends R1-S5; supplies the granularity requirements R2-F3 needs for P1. v0.4: Steps 3/5 + FR-RP-5. Test: `is_estimate(baseline_stub)` is False; per-FR provenance round-trips. | 2026-07-02 |
| R1-S5 | Downgrade the self-check's FR-RP-2 (→ Partial until owner-resolution owned) and FR-RP-5 (→ Partial until a distinct baseline provenance constant) | claude-opus-4-8-1m (R1) | ACCEPT — **medium**. Honest coverage correction. v0.4: update the self-check matrix; the FR-RP-5 fix is the **two-part** R2-S3 change (distinct value **and** per-FR granularity), not just avoiding `ESTIMATE_PROVENANCE`. | 2026-07-02 |
| R2-S5 | Reconcile R1-F5 ↔ R1-S2: adopt blockquote-demotion as the neutralize primitive **and** redefine the gate criterion to "a **line-start** `^#{1,6}`/setext heading survives ⇒ fail" | claude-opus-4-8-1m (R2) | ACCEPT — **medium**. Resolves the internal contradiction (a `> ## x` blockquote is safe for `^`-anchored CRP `####` parsing → demotion passes; a bare `^## x` fails). v0.4: Step 4 + Step 6.5. Test: demoted `> ## x` passes the gate; bare `^## x` fails; CRP `####` parse sees no injected section. | 2026-07-02 |
| R1-S4 | §7 add three tests: (a) owner-resolution vs a requirements roster, (b) FR-RP-9 discoverability pointer, (c) the readiness gate | claude-opus-4-8-1m (R1) | ACCEPT — **medium**. Closes the validation gaps R1-S1/R1-S2/FR-RP-9 opened. v0.4: §7 Validation Strategy. The three named tests pass. | 2026-07-02 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet — all R1–R2 S-suggestions accepted; see Appendix A) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

*(No review rounds yet.)*

#### Review Round R1 — claude-opus-4-8-1m — 2026-07-02

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-02 00:00:00 UTC
- **Scope**: Plan (S-prefix) — code-grounded against live `stakeholder_panel/`. Focus-file asks answered in the requirements-file R1 block; coverage matrix appended below.

##### Executive summary

- **Blocking**: Step 3 + Planning-discoveries row 4 claim `resolve_owner` is "reusable as-is (keys on a symbol string)". It is not — `input_domains.resolve_owner` calls `get_domain()` and returns `None` for any non-value-DOMAIN name, so every requirements area would be skipped (R1-S1).
- **Circularity**: generator's only correctness check is the CRP it feeds; add a $0 deterministic pre-CRP readiness gate (R1-S2) — resolves OQ-RP-8 toward a *blocking* check, not just an advisory score.
- **TOCTOU / clobber**: Step 6 "stale-session refuse" has no defined detection mechanism and a check→write race (R1-S3).
- **Internal contradiction**: CLI Step 6 marks `synthesize` as `$0`, but Risk R2 calls synthesis "the hard LLM step / least-deterministic". Clarify the $0-vs-LLM boundary inside synthesis (R1-S6).
- **Coverage overclaim**: self-check marks FR-RP-2 Full though it depends on the non-working `resolve_owner` reuse (R1-S5).
- **Validation gaps**: §7 has no test for owner-resolution-with-a-requirements-roster, for FR-RP-9 discoverability, or for the readiness gate (R1-S4).

##### Plan Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Interfaces | high | Correct Step 3 and Planning-discoveries row 4: `route()` is reusable, but `resolve_owner` is **not** — own a `RequirementDomain`-aware owner resolver (default `owning_role` on roster → high-confidence `answers_for` → skip). Fix the "reusable as-is" claim and the `routing.route` co-location of `resolve_owner` (it is in `input_domains.py`). | `input_domains.resolve_owner:308-325` calls `get_domain(domain_name)` (line 316) and returns `None` for any name outside `business-targets`/`conventions`/`build-preferences`, and keys on `spec.owning_role`. Reusing it verbatim would skip every requirements domain → zero drafts. | Step 3; Planning discoveries table row 4 | Test: `resolve_owner("security", briefs)` returns `None`; the new resolver returns the owning role for a requirements roster. |
| R1-S2 | Validation | high | Add Step 6.5 — a **$0 deterministic pre-CRP readiness gate** that blocks `approve` (does not auto-approve) when: any non-`<needs-owner>` candidate carries an unresolved grounding flag on a MUST/SHALL, any `<needs-owner>` stub was promoted, or any injected heading was only demoted (not removed). | Breaks the FR-RP-6 circularity (generator checked only by the CRP it feeds; focus ask 4 / OQ-RP-8) with a deterministic gate, not an advisory score. | New Step 6.5; ties OQ-RP-8 | Test: a run with an ungrounded `$2M ARR` intent FR refuses approve until resolved. |
| R1-S3 | Risks | high | Step 6 must define stale-session detection (target-path exists / content-hash mismatch) **and** make the existence-check + write atomic (`O_EXCL`/`os.link`), not a check-then-`os.replace` (TOCTOU). | `ProposalStore`'s atomic `mkstemp`+`os.replace` guarantees atomic *staging* but does not stop clobbering an existing `*_REQUIREMENTS.md`; a concurrent creation between the stale-check and the write would be overwritten. | Step 6; Risks (new R5) | Test: pre-existing target → refuse, byte-unchanged; concurrent-create race → no clobber. |
| R1-S4 | Validation | medium | §7 add three tests: (a) owner-resolution against a **requirements roster** (owned→drafts, un-owned→skip, never a loose match); (b) FR-RP-9 discoverability pointer emitted from the reflective-loop/Concierge "no reqs doc" gap; (c) the R1-S2 readiness gate. | §7 currently proves grounding/synthesis/sanitization/isolation but not routing-with-the-new-resolver, the discoverability surface, or readiness. | §7 Validation Strategy | The three named tests pass. |
| R1-S5 | Validation | medium | Downgrade the self-check's FR-RP-2 from Full to **Partial** until owner-resolution is owned (R1-S1); FR-RP-5 to **Partial** until a distinct `$0-baseline` provenance constant (not `ESTIMATE_PROVENANCE`, which carries model+role) is specified. | The coverage self-check claims Full on FR-RP-2 while Step 3 relies on a reuse that does not work; `ESTIMATE_PROVENANCE` (recommend_provenance) encodes model/role a no-LLM baseline lacks. | Requirements Coverage (self-check) table | Reconcile against the R1 coverage matrix below. |
| R1-S6 | Architecture | medium | Reconcile the synthesis determinism boundary: CLI Step 6 marks `synthesize` `$0`; Risk R2 calls it "the hard LLM step". State explicitly which sub-steps are $0 (dedupe/ID/order) and whether conflict-framing invokes an LLM (and if so, its cost/provenance). | A reader cannot tell if synthesis spends; FR-RP-3 reads fully deterministic, Risk R2 reads LLM-driven — a dual-doc inconsistency that changes cost and the bucket-3 story. | Step 5 / Risk R2 / FR-RP-3 | AC states synthesis cost class; test asserts `synthesize` makes no LLM call if declared $0. |

**Endorsements**: none (no prior rounds).
**Disagreements**: none (no prior rounds).

#### Review Round R2 — claude-opus-4-8-1m — 2026-07-02

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-02 00:00:00 UTC
- **Scope**: Plan (S-prefix) — adversarial second pass. Falsifies a **second** overclaimed reuse beyond R1-S1, surfaces cost/provenance leaks in the synthesis step, and reconciles two untriaged R1 items that pull in opposite directions. Coverage delta in the R2 matrix at file end.

##### Executive summary (R2)

- **"Mirror `recommend_inputs`" overclaims twice**: R1-S1 caught `resolve_owner`; the *same* mirror also inherits `_default_domains`, which enumerates domains by **YAML file presence** (`DOMAINS[name].rel_path().is_file()`, recommend.py:162-168) — requirements domains are an in-code `RequirementDomain` registry with no YAML, so enumeration must also be owned (R2-S1).
- **Risk R1 mitigation cites a non-reused private symbol** — the temporal-safety property lives in private `_temporal`/`_MONTH_DATE`; the plan writes a new `extract_temporal` that need not inherit it (R2-S2).
- **Provenance shape mismatch**: `ESTIMATE_PROVENANCE`+`is_estimate` require a `panel:<role>` origin (recommend_provenance.py:44-46) a `$0` baseline stub lacks, and the synthesized doc needs per-FR (not doc-level) provenance (R2-S3).
- **No post-CRP re-elicit lifecycle** (beyond R1-S3's race): once the doc is versioned/human-owned, re-`elicit` must refuse forever — undefined today (R2-S4).
- **R1-F5 ↔ R1-S2 conflict**: neutralize-by-blockquote vs "demoted heading ⇒ gate-fail" contradict; pick one (R2-S5).
- **Synthesis-generated text bypasses sanitize+ground** (Step 4 runs *before* Step 5): if conflict-framing spends (R1-S6), its output enters the doc unsanitized/ungrounded (R2-S6).

##### Plan Suggestions (R2)

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Interfaces | high | Replace Step 3's "mirror `recommend_inputs`'s signature/flow" with an explicit **reuse-vs-own** table. Reusable: `panel.ask`/`preflight_budget`/`telemetry.span`/`routing.route`. **Owned**: domain enumeration *and* owner resolution (R1-S1) *and* grounding. `_default_domains` is not reusable — it is file-driven. | `recommend._default_domains` (recommend.py:162-168) walks `SUPPORTED_DOMAINS` and includes a domain only if `DOMAINS[name].rel_path().is_file()`. Requirements domains are the in-code `RequirementDomain` registry with **no** on-disk YAML, so a verbatim mirror enumerates **zero** domains — a second silent no-op in the same "mirror" claim R1-S1 already dented. | Step 3; Planning-discoveries row 4 | Test: assert no requirements-panel code path calls `recommend._default_domains`; the owned enumerator returns the `RequirementDomain` registry names. |
| R2-S2 | Data | high | Step 2 must state that the owned `extract_temporal` **ports** the private `_MONTH_DATE` bare-month exclusion + day-adjacency and the `_YEAR` behavior; otherwise strike the Risk R1 mitigation clause that cites grounding_guard.py:39-46. | Risk R1's mitigation ("the guard already drops bare month words — grounding_guard.py:39-46") points at `_temporal`, which is **private** (not exported, grounding_guard.py:26-31) and **not** reused. The plan reuses only `extract_money`/`extract_percent`. The cited prose-safety property is therefore unproven unless Step 2 explicitly replicates it. Ties requirements R2-F1/R2-F2. | Step 2; Risk R1 | AC: the owned `extract_temporal` matches the private `_temporal` output on a fixture set (bare month → none; "March 2027" → flagged; bare year → advisory-low per R2-F2). |
| R2-S3 | Data | medium | Steps 3/5 must specify (a) a **distinct** `$0`-baseline provenance value (not `ESTIMATE_PROVENANCE`), and (b) a **per-FR** provenance carrier on `RequirementDoc`, not one doc-level stamp. | `ESTIMATE_PROVENANCE="estimate"` + `is_estimate` require `rec.origin.startswith("panel:")` (recommend_provenance.py:44-46); a no-LLM baseline stub has no persona origin, so `is_estimate` is False by construction and `assert_not_authored` guards nothing for it. Extends R1-S5; adds the per-FR granularity requirements R2-F3 needs for P1. | Steps 3, 5; FR-RP-5 | Test: `is_estimate(baseline_stub)` is False; a synthesized doc round-trips distinct per-FR provenance for a baseline stub vs a role FR. |
| R2-S4 | Risks | high | Add Risk R6 + a Step-6 clause: once a versioned `*_REQUIREMENTS.md` exists (created by a prior approve or edited by CRP/human), `elicit`/`approve` **refuse permanently** and point to edit-in-place — never regenerate over a human/CRP-owned doc. | R1-S3 fixes the check→write *race*; it does not fix the *lifecycle*. The doc's whole purpose is to go to CRP and evolve to v0.2+. A later `elicit` either permanently stale-refuses (dead capability) or clobbers CRP+human work (P1 violation). The spec has no post-CRP re-elicit story. | Step 6; new Risk R6 | Test: `elicit` against an existing v0.2 doc refuses with an edit-in-place pointer; no bytes change. |
| R2-S5 | Validation | medium | Reconcile R1-F5 and R1-S2: adopt blockquote-demotion as the neutralize primitive **and** redefine the readiness-gate criterion from "demoted ⇒ fail" to "a **line-start** heading (`^#{1,6}`/setext) survives ⇒ fail". A `> ## x` blockquote is safe for `^`-anchored CRP `####` parsing. | Two untriaged R1 items contradict: R1-F5 prefers neutralize-by-demote; R1-S2's gate fails approve if a heading was "only demoted (not removed)". Left unreconciled, triage accepts a spec that both requires and forbids demotion. | Step 4; new Step 6.5 (ties R1-S2) | Test: a `> ## x` demoted line **passes** the readiness gate; a bare `^## x` **fails**; CRP `####`-anchored parse sees no injected section. |
| R2-S6 | Ops | medium | If R1-S6 resolves synthesis conflict-framing to spend (LLM), Steps 4/5 must run sanitize+ground **on synthesis output**, not only on candidates — Step 4 (sanitize) currently precedes Step 5 (synthesize). | FR-RP-3 lifts cross-role conflicts into "## Open Questions" prose. If that text is LLM-generated (Risk R2 calls synthesis "the hard LLM step"), it enters the final doc **after** the only sanitize pass and with no grounding/provenance — an unsanitized-heading and ungrounded-specific leak that FR-RP-7/FR-RP-4 exist to stop. | Steps 4, 5; FR-RP-3/R2 | Test: a synthesis-generated OQ containing `## x` is neutralized and provenance-stamped; assert no un-sanitized text reaches the assembled doc. |

**Endorsements** (prior untriaged R1 items this reviewer agrees with):
- R1-S1: `resolve_owner` verbatim-reuse returns `None` for every requirements domain (confirmed input_domains.py:308-325 via `get_domain`) — owner resolution must be owned.
- R1-S2: a `$0` deterministic pre-CRP readiness gate is the right break for the FR-RP-6 circularity; make it blocking, not advisory (see R2-S5 for its exact heading criterion).
- R1-S3: stale-session detection + atomic `O_EXCL` write is necessary (but insufficient alone — see R2-S4 for the lifecycle half).

**Disagreements / refinements**:
- R1-S5 (extend, not reject): downgrading FR-RP-5 to Partial is right; add that the fix is *two* changes — a distinct baseline provenance value **and** per-FR granularity (R2-S3/R2-F3), not just avoiding `ESTIMATE_PROVENANCE`.

## Requirements Coverage Matrix — R1

Analysis only (reviewer view; the plan body's own self-check is the author view). "Plan reads Full" = the plan's self-check claim; "R1 assessment" = this review's code-grounded read.

| Requirement | Plan Step(s) | Plan reads | R1 assessment | Gap |
| ---- | ---- | ---- | ---- | ---- |
| FR-RP-1 (`$0` baseline) | Step 1 | Full | Partial | "primary entity" undefined; join/compound-`@@id` handling unspecified (R1-F6). |
| FR-RP-2 (role drafting via `panel.ask`) | Step 3 | Full | **Partial** | Depends on `resolve_owner` reuse that returns `None` for all requirements domains (R1-S1/R1-F1); owner-resolution must be owned. `panel.ask` reuse itself is sound (panel.py:172). |
| FR-RP-3 (synthesis, no overwrite) | Step 5 | Full | Partial | Dedupe rule + ID stability under-defined (R1-F3/R1-F4); $0-vs-LLM boundary contradicts Risk R2 (R1-S6). |
| FR-RP-4 (project-grounding guard) | Step 2 | Full | Partial | Extractor reuse sound (grounding_guard.py:68-69); "soften" undefined (R1-F2); entity-absence should be a harder flag than fuzzy specifics (Ask 2). |
| FR-RP-5 (provenance) | Steps 3, 5 | Full | Partial | `$0` baseline needs a distinct provenance constant; `ESTIMATE_PROVENANCE` carries model/role a no-LLM baseline lacks (R1-S5). |
| FR-RP-6 (file-write apply + CRP gate) | Steps 6, 7 | Full | Partial | Stale-session detection + atomic write (TOCTOU) unspecified (R1-S3); no pre-CRP readiness gate (R1-S2). |
| FR-RP-7 (heading sanitization) | Step 4 | Full | Partial | `^#{2,4}\s` misses h1/h5/h6 + setext (R1-F5). |
| FR-RP-8 (elicit→synthesize→review→approve loop) | Step 6 | Full | Full | `review` renders literal bytes (R3-S2 discipline); staging mirrors `ProposalStore`. |
| FR-RP-9 (discoverable from reflective loop) | Step 7 | Full | Partial | No validation of the discoverability pointer (R1-S4b). |

## Requirements Coverage Matrix — R2

Analysis only (reviewer view). "R2 delta" = what this adversarial round changes vs the R1 assessment above; unchanged rows are omitted intent-wise but listed for completeness. R2 does not re-litigate R1 items — it adds second-order gaps.

| Requirement | Plan Step(s) | R1 assessment | R2 assessment | R2 delta (new this round) |
| ---- | ---- | ---- | ---- | ---- |
| FR-RP-1 (`$0` baseline) | Step 1 | Partial | Partial | "primary entity" now has a concrete deterministic rule available — `PrismaModel.compound_unique_keys()` excludes join tables (R2-F5). |
| FR-RP-2 (role drafting via `panel.ask`) | Step 3 | Partial | **Partial (worse)** | The "mirror `recommend_inputs`" claim fails a **second** time: `_default_domains` is YAML-file-driven and enumerates zero requirements domains (R2-S1), on top of the R1-S1 `resolve_owner` break. |
| FR-RP-3 (synthesis, no overwrite) | Step 5 | Partial | Partial | Synthesis-generated OQ text bypasses the sanitize (Step 4) + ground passes if conflict-framing spends (R2-S6); ties R1-S6. |
| FR-RP-4 (project-grounding guard) | Step 2 | Partial | **Partial (worse)** | The cited prose-safety control references private, non-reused `_temporal` (R2-S2/R2-F1); `_YEAR` floods requirement prose with false flags (R2-F2). |
| FR-RP-5 (provenance) | Steps 3, 5 | Partial | Partial | Two fixes needed, not one: distinct baseline provenance value **and** per-FR (not doc-level) granularity, or P1's "never indistinguishable" fails on a mixed doc (R2-S3/R2-F3). |
| FR-RP-6 (file-write apply + CRP gate) | Steps 6, 7 | Partial | Partial | Beyond the R1-S3 race: no post-CRP re-elicit lifecycle — a later `elicit` either dead-refuses or clobbers CRP/human work (R2-S4). |
| FR-RP-7 (heading sanitization) | Step 4 | Partial | Partial | Neutralize strategy (R1-F5) conflicts with the R1-S2 readiness-gate criterion; reconcile on line-start-anchored detection (R2-S5). |
| FR-RP-8 (loop + surface) | Step 6 | Full | **Partial** | `review` "literal bytes" has no defined surface for advisory grounding flags — approver may never see them, or they pollute the CRP-parsed doc (R2-F4). |
| FR-RP-9 (discoverable) | Step 7 | Partial | Partial | Unchanged from R1-S4b. |
