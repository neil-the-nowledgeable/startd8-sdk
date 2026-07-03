# Requirements Panel — Implementation Plan

**Version:** 0.1
**Date:** 2026-07-02
**Requirements:** `REQUIREMENTS_PANEL_REQUIREMENTS.md` (v0.3)
**Branch:** `feat/requirements-panel-spec` (design-only; code lands on a later `feat/requirements-panel`).

---

## Planning discoveries (fed the reflection pass)

| What v0.1 assumed | What planning (live-code read) revealed | Impact |
|-------------------|-----------------------------------------|--------|
| `grounding_guard.unsupported_specifics` grounds against the project brief | `grounding_guard.py:81-89` — `_brief_corpus` is `goals+constraints+known_positions+display_name` of **the persona's own brief**. It grounds a persona's answer against *that persona's* stated positions, not the project. | **FR-RP-4 owns `ground_requirement`** with a **project corpus** (problem-statement brief + schema entity/field names), reusing only the guard's `extract_money`/`extract_percent` (publicly exported at `grounding_guard.py:68-69`) + a temporal extractor. |
| A drafted requirement, being an estimate, should suppress the specifics check like values do | `recommend.py:130-133` — comment: *"Do NOT carry the reactive unsupported-specifics flags — an estimate is expected to introduce a value the brief never stated."* Only `check_contradiction` runs on value drafts. | **Requirements invert this**: a fabricated `"40% faster"` **is** the failure. FR-RP-4 **runs** the specifics check; the estimate-suppression rationale does not apply to intent prose. |
| Approve reuses the `manifest` proposal kind (Manifest-Suggester template) | No requirements shape in `kickoff_experience/proposals.py:PROPOSAL_KINDS`; requirements are markdown in `docs/design/`, not a `CONVENTION_PATHS`-mapped manifest. | **FR-RP-6 apply = CLI markdown file-write** at human privilege; **CRP is the second gate**. No `PROPOSAL_KINDS` change (NR-RP-3). |
| `input_domains.py` is the "what to draft" layer to reuse | `input_domains.py:79-101,208-248` models **scalar YAML `FieldSlot`s** (dotted keys, composite `{target,why}`); requirements units are prose sections/FR-classes. | **FR-RP-1 owns `RequirementDomain`** — the *structural analogue* of `DomainSpec` (area name, owning role, prompt template, grounding hooks), not a reuse. `resolve_owner`/`route` **are** reusable as-is (they key on a symbol string). |
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
- `baseline.py`: `scaffold(brief, schema_text) -> RequirementDoc` — deterministic (`$0`) Problem gap
  table + one entity-touching FR **stub** per primary entity (via `languages/prisma_parser`), standard
  `## Non-Requirements` / `## Open Questions` headings, unfilled areas marked `<needs-owner>`. **No LLM.**

### Step 2 — Project-grounding guard (FR-RP-4, owned — NOT the panel's)
- `grounding.py`: `ground_requirement(candidate, project_corpus, schema) -> Ok|Flag(reasons)`.
  - `project_corpus` = brief text + declared entity/field names.
  - Reuse `grounding_guard.extract_money`/`extract_percent`; add `extract_temporal`; flag any
    money/percent/date specific not in the corpus, and any entity/field reference absent from the schema.
  - Advisory (flag + soften), never a hard block (P3); CRP is authoritative.

### Step 3 — Role-informed drafting (FR-RP-2, reuse `panel.ask`/`routing`)
- `elicit.py`: `async elicit_requirements(package_root, panel, brief, schema, *, domains=None, cap=None,
  session_id=None) -> ElicitationRun` — **mirror `recommend_inputs`'s signature/flow**
  (`recommend.py:164`): enumerate domains → `routing.route(briefs, area)` / bounded `resolve_owner`
  → budget-preflight the resolved+capped set → `await panel.ask(owner, drafting_prompt, value_path=area)`
  → skip `UNAVAILABLE`/`DEFERRED` (never fabricate) → run Step 2 grounding → stage `RequirementCandidate`s
  (`estimate` provenance). Prompt carries **brief + literal declared entity names** (Manifest-Suggester
  R2-S3/R2-F3). Under a parent span `requirements.elicit_pass` (reuse `telemetry.span`, mirror
  `stakeholder.recommend_pass`). Paid; the Step-1 `$0` baseline runs without it.

### Step 4 — Sanitization (FR-RP-7, before synthesis)
- `sanitize.py`: `neutralize_headings(text) -> text | Reject` — scan every candidate free-text field for
  `^#{2,4}\s`; reject the candidate (preferred) or demote the line to a blockquote, so no injected
  section reaches the assembled doc or the later CRP appendix. (Manifest-Suggester R3-S1.)

### Step 5 — Synthesis pass (FR-RP-3, owned)
- `synthesis.py`: `synthesize(baseline, candidates) -> RequirementDoc` — dedupe near-identical FRs
  across roles (slug/normalized text), assign stable `FR-<AREA>-<n>` IDs, order by area, lift cross-role
  conflicts into `## Open Questions` (never drop silently). Emits the **whole** doc (R2-S1 discipline).

### Step 6 — draft → review → approve loop + store (FR-RP-8, mirror the panel)
- `store.py` stages the run out-of-band — **mirror `ProposalStore`'s shape** (atomic `mkstemp`+`os.replace`,
  `sort_keys`+`indent=2`, session GC, `_safe_session_component` traversal guard). CLI
  `cli_requirements.py` (`startd8 requirements`): `elicit` (`$0` baseline + optional `--roles`) ·
  `synthesize` (`$0`) · `review` (`$0` render of the **literal** doc bytes that approve would write —
  Manifest-Suggester R3-S2) · `approve`/`reject` → `apply.py` writes the markdown file at human
  privilege + prints the CRP hand-off command (FR-RP-6). Stale-session refuse (no clobber).

### Step 7 — CRP hand-off + reflective-loop discoverability (FR-RP-6/9)
- `approve` emits the ready-to-run `/new-cnvrg-rvw-prmpt --plan … --requirements …` invocation (dual-doc)
  and a one-line pointer from the `reflective-requirements` entry point / Concierge "no reqs doc" gap.

### Step 8 — Tests
- `$0` baseline: brief+schema → a scaffold with an entity-touching FR stub per primary entity, no
  invented intent (all `<needs-owner>`), **no LLM call**.
- Grounding: a candidate asserting `"$2M ARR"` unsupported by the brief is flagged; an FR naming a
  non-existent entity is flagged; a supported specific passes.
- Panel reuse: `elicit_requirements` goes through `panel.ask` (cost/transcript/span recorded), never a
  bare `Persona`; un-owned area → skipped, never a loose match.
- Sanitization: a candidate whose rationale contains `### Non-Requirement:` is rejected/neutralized
  before synthesis; the assembled doc has only intended headings.
- Synthesis: two roles drafting the same FR → one deduped entry; a cross-role conflict → an Open
  Question, never a silent drop; approving assembles the **whole** doc (both roles' FRs present).
- Apply: approve writes the markdown at the target path at human privilege; a pre-existing target →
  stale-refuse, no clobber; the CRP hand-off command is printed.

---

## §7 Validation Strategy
- **Bucket boundary (P1):** a test asserts every drafted candidate + the synthesized doc carry
  `estimate`/`$0`-baseline provenance and that approve requires an explicit human action (no
  auto-approve path exists).
- **Dual grounding (P3):** brief-only and schema-only fixtures each catch their class of fabrication;
  a doubly-supported specific passes both.
- **No-silent-overwrite (R2-S1):** synthesizing/approving N role contributions yields all N in the
  final doc, never just the last.
- **Sanitization (R3-S1):** injected `##`/`####` lines never survive into the assembled doc or the CRP
  appendix scaffold.
- **Reuse-not-fork:** `elicit_requirements` imports `panel`/`routing`/`ProposalStore` but adds no value
  domain and no proposal kind; `PROPOSAL_KINDS` unchanged.
- **Panel-isolation (NR-RP-1):** the stakeholder-panel value pass is untouched.

## Risks
- **R1 — Grounding false-positives/negatives on prose.** The specifics extractors were tuned for scalar
  value answers; requirement prose is longer. Mitigation: advisory-only (P3) + CRP as authoritative
  gate; tune the temporal extractor conservatively (the guard already drops bare month words for this
  reason — `grounding_guard.py:39-46`).
- **R2 — Synthesis quality (the hard LLM step).** Merging multi-role drafts into a coherent doc is the
  least-deterministic step. Mitigation: keep synthesis mechanical where possible (dedupe/ID/order are
  `$0`); only conflict-framing needs judgment, and unresolved conflicts degrade to Open Questions, not
  silent choices.
- **R3 — Scope creep past bucket-4.** The capability could drift toward "writing the real requirements."
  Mitigation: P1 scope lock + provenance on every unit + human-approve-only + CRP second gate.
- **R4 — Roster coupling.** Mitigation: reuse `persona`/`routing`/`roster` only (generic); ship a
  default requirements roster (OQ-RP-7) keyed on FR-area `answers_for`, no new roster grammar.

---

## Requirements Coverage (self-check, pre-CRP)

| Requirement | Plan Step(s) | Coverage |
|-------------|-------------|----------|
| FR-RP-1 (`$0` baseline) | Step 1 | Full |
| FR-RP-2 (role drafting via `panel.ask`) | Step 3 | Full |
| FR-RP-3 (synthesis, no overwrite) | Step 5 | Full |
| FR-RP-4 (project-grounding guard) | Step 2 | Full |
| FR-RP-5 (provenance) | Steps 3, 5 | Full |
| FR-RP-6 (file-write apply + CRP gate) | Steps 6, 7 | Full |
| FR-RP-7 (heading sanitization) | Step 4 | Full |
| FR-RP-8 (elicit→synthesize→review→approve loop) | Step 6 | Full |
| FR-RP-9 (discoverable from reflective loop) | Step 7 | Full |

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

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| (none yet) |  |  |  |  |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

*(No review rounds yet.)*
