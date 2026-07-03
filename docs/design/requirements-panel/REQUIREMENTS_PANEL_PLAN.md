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
