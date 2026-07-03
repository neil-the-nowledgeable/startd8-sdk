# Manifest Suggester — Implementation Plan

**Version:** 0.1
**Date:** 2026-07-02
**Requirements:** `MANIFEST_SUGGESTER_REQUIREMENTS.md` (v0.1)
**Branch:** `feat/manifest-suggester` (worktree off `origin/main`).

---

## Planning discoveries (feed the reflection pass)

| What v0.1 assumed | What planning (code read) revealed | Impact |
|-------------------|-----------------------------------|--------|
| A schema-grounded **CRUD baseline** (a list/detail page per entity) is the core value (FR-MS-1) | **`pages.yaml` is for *owned, non-entity* content pages** — `pages_generator.py:1`: "Content-pages generator … non-entity pages from a `pages.yaml` manifest." **Entity CRUD is auto-generated from the schema by the cascade** (no manifest needed). A CRUD-per-entity baseline would duplicate what's already `$0`. | **FR-MS-1 reframed (big):** the suggester proposes **composite views** (dashboard/board/workspace over entities) + **non-entity content pages** — NOT entity CRUD. Schema-grounding = reference real entities *inside* composites, not enumerate CRUD. |
| Baseline + role-informed are two separate tiers | Both target the **same** non-obvious composite/content screens (a dashboard, a funnel, an admin page). The only `$0` baseline that isn't redundant is "a starter dashboard view over your primary entities." | **FR-MS-1/2 merge:** the value is the non-obvious screens; the `$0` baseline shrinks to a groundable starter composite, the paid role pass adds the rest. |
| "Reuse the panel infra" broadly (FR-MS-2/7) | **Partial:** `persona.Persona.ask(question, value_path)` and `routing.route/persona_matches(brief, value_path)` are **generic** (keyed on a `value_path`-like symbol) — REUSABLE. But `recommend.py`/`input_domains.py`/`recommend_apply.py` are **hard-bound to scalar value-input fields + the strict value parser**, and `grounding_guard` grounds against the *value corpus*, not schema entities — NOT reusable. | **FR-MS-2/7 narrowed:** reuse **persona + routing + roster + the recommend→review→approve *pattern***; the suggester has its **own** recommend/apply/grounding (manifest-shaped, schema-anchored). |
| The `manifest` kind may need a dest hint (OQ-2) | `_apply_manifest` takes **prose `source` only, never a path** (R1-F2); the server extracts + maps to `CONVENTION_PATHS` (round-trip-gated, no-clobber, all-or-nothing). | **OQ-2 resolved:** an approved screen → a `manifest` proposal with `source` = emitted prose. No new apply path, no dest hint. FR-MS-5 confirmed. |
| Prose grammar unknown (OQ-1) | Views = `view: <name>` sections with a `Kind ∈ {dashboard/board/workspace}` (`extract_views`); pages = `## Pages` rows (`extract_pages`); heading-delimited markdown. | **OQ-1 resolved:** the suggester emits this markdown; the extractor round-trips it. |
| A new "screens" roster role is needed (OQ-4) | The roster is generic (`role_id` + `answers_for` prefixes); routing matches `answers_for` to a `value_path` symbol. A design/PM persona with `answers_for` naming `views`/`pages` routes — **no new roster grammar**, just roster *content*. | **OQ-4 resolved:** model screens as a `value_path`-like symbol (`views`/`pages`); a design/PM persona owns it. |

**Net:** the loop killed the CRUD-baseline (redundant with `$0` codegen) and sharpened the capability to
**suggesting composite views + non-entity pages**, reusing persona/routing/the `manifest` kind but owning a
manifest-shaped recommend/apply/grounding.

---

## Approach & step map

### Step 1 — The schema-grounded candidate model (FR-MS-1/4, corrected)
- New `src/startd8/manifest_suggester/` package. `candidates.py`:
  - `schema_entities(root) -> EntityFacts` via `languages/prisma_parser` (primary/non-join models, key
    relations) — the grounding vocabulary.
  - `baseline_views(facts) -> list[ScreenCandidate]` — a `$0` starter **dashboard view** over the primary
    entities (a composite, groundable), emitted as `view: <name>` + `Kind: dashboard` prose. **No CRUD.**
  - `ScreenCandidate{kind: page|view, name, prose, entities_referenced, provenance}`.

### Step 2 — Grounding guard (FR-MS-4, schema-anchored — NOT the panel's)
- `grounding.py`: `ground(candidate, facts) -> Ok|Reject(reason)` — every `entities_referenced` must be a
  declared entity/field; reject unknown-entity candidates **before** the `manifest` apply's round-trip.

### Step 3 — Role-informed drafting (FR-MS-2, reuse persona/routing)
- `suggest.py`: reuse `stakeholder_panel.persona.Persona` + `routing.route` — route the "screens" symbol
  (`views`/`pages`) to its owning persona (bounded: owner or high-confidence `answers_for`, else skip). Ask
  the persona to draft non-obvious composites/pages **grounded in the entity facts** (the prompt carries the
  entity list). Parse the reply into `ScreenCandidate`s; run Step 2's grounding guard. Paid; `$0` baseline
  (Step 1) runs without it.

### Step 4 — Dedupe against the live manifest (FR-MS-3, OQ-6)
- Read the current `views.yaml`/`pages.yaml` (reuse the wireframe inventory / a small reader) → skip
  candidates whose name/slug already exists.

### Step 5 — draft → review → approve (FR-MS-7, mirror Teian pattern)
- `store.py` stages candidates out-of-band (session store, stale detection). CLI `cli_manifest_suggester.py`
  (or `startd8 screens`): `suggest` (baseline `$0` + optional `--roles` paid pass) · `review` (`$0` render) ·
  `approve`/`reject` → emits a **`manifest` proposal** (`source` = the candidate's prose) applied via
  `apply_proposal` at human privilege (FR-MS-5). Provenance marker on each (FR-MS-6).

### Step 6 — Surface the Red Carpet screens gap (FR-MS-8)
- When the advisor/wizard reports the screens gap, add a next-step/command pointing at `startd8 screens
  suggest` (discoverable at the moment of need). Presentation-only (glossary-plain per KICKOFF_UX).

### Step 7 — Tests
- Baseline: a schema → a groundable starter dashboard view (no CRUD pages); grounding guard rejects an
  unknown-entity candidate; dedupe skips an already-present screen; an approved candidate → a `manifest`
  proposal whose prose round-trips through `extract_views`/`extract_pages`; propose-confirm floor (no writes
  without approve); role routing bounded (un-owned screens symbol → skip, never a loose match).

---

## §7 Validation Strategy
- **No-CRUD-duplication:** the baseline emits composite views / non-entity pages only — a test asserts it
  never emits an entity-CRUD page (that's the cascade's job).
- **Schema-grounding:** a candidate referencing a non-existent entity is rejected before apply; an
  approved candidate's prose re-parses through the real extractor (round-trip).
- **Propose-confirm floor:** the loop never writes; every screen is a `manifest` proposal.
- **Reuse-not-fork:** the apply goes through the existing `manifest` kind (no new write path); a test
  asserts `PROPOSAL_KINDS` is unchanged.
- **Panel-isolation (NR-1):** the stakeholder-panel value pass is untouched; the suggester imports
  persona/routing but adds no value-domain.

## Risks
- **R1 — Baseline redundancy with `$0` CRUD gen.** Mitigation: the baseline is composites/non-entity pages
  only (the CRUD-duplication test).
- **R2 — Hallucinated entities from the role pass.** Mitigation: the schema grounding guard + the
  extractor round-trip (two gates).
- **R3 — Roster coupling.** Mitigation: reuse `persona`/`routing` only (generic); no dependency on the
  value-domain `recommend`/`input_domains`.

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

### Areas Substantially Addressed (>= 3 accepted)

- **Validation**: 3 accepted (R1-S3, R2-S3, R3-S2)

### Areas Needing Further Review (below threshold of 3)

- **Architecture**: 2/3 accepted (R1-S5, R2-S2)
- **Risks**: 2/3 accepted (R1-S7, R2-S1)
- **Security**: 2/3 accepted (R1-S6, R3-S1)
- **Interfaces**: 1/3 accepted (R1-S1)
- **Data**: 1/3 accepted (R1-S2)
- **Ops**: 1/3 accepted (R1-S4)

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R2-S1 | Explicit accumulation strategy for the whole-file-replace apply seam (`_apply_manifest` derives the entire write from one candidate's `source`, no merge with on-disk YAML) | claude-sonnet-5 (R2) | ACCEPT — **critical, build-blocking**. Adopt option (a): `store.py`/CLI keeps a running authoring-prose document; every `approve` re-emits the **whole accumulated document** as `source` with `replace=true`. Defer option (b) YAML→prose decompiler unless a screen authored outside the suggester must be preserved. Test: approve 2 candidates in sequence against an initially-empty manifest → **both** views present in final `views.yaml`. | 2026-07-03 |
| R3-S1 | Sanitize every free-text field (rationale / persona description) for a line matching `grammar._HEADING_RE` (`^#{2,4}\s`) before render or apply | claude-sonnet-5 (R3) | ACCEPT — **critical, security**. `parse_sections` is a pure line-scanner; any `##`/`###`/`####` line becomes a section boundary. Prefer **reject-the-candidate** over escaping. Any accumulation doc from R2-S1 must re-run this on the fully assembled `source` (see R3 endorsement). Test: injected `### view: Injected` in a rationale is rejected before `_apply_manifest`; `extract_manifests` on final `source` yields only the intended view. | 2026-07-03 |
| R1-S1 | Change Step 3 reuse target from bare `Persona.ask` to `StakeholderPanel.ask` (mirror `recommend_inputs(package_root, panel, ...)`) | claude-sonnet-5 (R1) | ACCEPT — high. `Persona.ask` bypasses cost tracking, transcript, budget preflight, OTel spans (all live in `panel.py`). `suggest.py` takes the live `panel`, calls `panel.ask(role_id, ...)` after `routing.route()`. Test: `suggest_screens` never imports `Persona` directly; cost/telemetry assertions parallel `recommend_inputs`. | 2026-07-03 |
| R1-S2 | Rewrite `baseline_views`: pick **one** `Root` entity, add `Shows:`/`counts of` only for entities `EntityGraph.join_between` connects to the root; degrade to relation-free dashboard when no join exists | claude-sonnet-5 (R1) | ACCEPT — high. `extract_views` resolves a single `Root`; naive "primary entities" (plural) risks the `$0` baseline failing its own round-trip. Test: 3-entity schema, only 2 joined → baseline references exactly those 2. | 2026-07-03 |
| R2-S2 | Define `EntityFacts` as a wrapper over / alias for `manifest_extraction.entities.EntityGraph` (`graph_from_prisma(parse_prisma_schema(...))`), not a parallel type | claude-sonnet-5 (R2) | ACCEPT — high. Guarantees the grounding guard's "grounded" verdict and the extractor's "round-trips" verdict cannot diverge. Underpins R1-S2 and R1-S3. Test: shared fixture through both paths → identical `resolve_entity`/`join_between`. | 2026-07-03 |
| R3-S2 | `review`'s `$0` render must show the **literal bytes** of the `source` that `approve` submits, not a summary | claude-sonnet-5 (R3) | ACCEPT — high. Anti-anchoring (mirrors sibling FR-KIR-9); the promotion gate is only real if the human sees exactly what is extracted. Test: review-output snapshot is byte-identical to the `approve` `source`. | 2026-07-03 |
| R1-S3 | Broaden Step 2 `ground()` to also check Kind-vocabulary membership + Kind-specific required keys (`board` → `Group by`), OR explicitly scope it as a necessary-but-not-sufficient pre-filter with the round-trip authoritative | claude-sonnet-5 (R1) | ACCEPT — medium. Do **both**: add the cheap Kind/`Group by`/`Shows`-join checks AND document the two-gate division so "guard passed / round-trip failed" reads as expected. One Step-7 test per rejection class. | 2026-07-03 |
| R2-S3 | Drafting prompt (Step 3) must hand the persona the **literal declared entity name strings** from `EntityFacts`/`EntityGraph.entities` and require verbatim reference | claude-sonnet-5 (R2) | ACCEPT — medium. `resolve_entity` normalizes only case/plurality/punctuation vs the exact name; free paraphrase ("the customer's profile") fails grounding for a prompt-design reason. Test: verbatim `CustomerProfile` grounds; paraphrase does not. | 2026-07-03 |
| R1-S7 | Dedupe (Step 4) by the extractor-derived slug (`nfkd_kebab` `ident`), not raw `name` equality | claude-sonnet-5 (R1) | ACCEPT — medium. Case/punctuation-different names collide at the extractor/route layer. Test: existing `Signup Funnel` vs candidate `signup-funnel` deduped at Step 4, not at apply. | 2026-07-03 |
| R1-S5 | Promote the `ProposalStore` shape (atomic `mkstemp`+`os.replace`, `sort_keys`+`indent=2`, `latest_session`/`session_ids`/`gc_stale_proposals`, `_safe_session_component` traversal guard) as the reference for `store.py` | claude-sonnet-5 (R1) | ACCEPT — medium. Reuse-not-reimplement (P5); every edge case is already CRP-hardened in the sibling feature. `store.py` on-disk shape asserted against `ProposalStore`'s contract in a shared test helper. | 2026-07-03 |
| R1-S4 | Wrap the paid pass in a parent OTel span analogous to `stakeholder.recommend_pass`, reusing `stakeholder_panel.telemetry.span` | claude-sonnet-5 (R1) | ACCEPT — medium. Cheap, proven precedent; keeps the suggester's paid calls consistent with every other panel-adjacent surface. Trace: `panel.ask` spans nest under a `screens.suggest_pass` parent. | 2026-07-03 |
| R1-S6 | Have `store.py` mirror `ProposalStore`'s at-rest posture (`0700` dir + atomic tmp+replace) rather than plain `json.dump` | claude-sonnet-5 (R1) | ACCEPT — low. Staged screens hold LLM-drafted prose tied to project internals; same sensitivity as staged recommendations. Folds into R1-S5's implementation. File-permission assertion in the R1-S5 test. | 2026-07-03 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet — all R1–R3 S-suggestions accepted; see Appendix A) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-sonnet-5 — 2026-07-03 01:50:00 UTC

- **Reviewer**: claude-sonnet-5
- **Date**: 2026-07-03 01:50:00 UTC
- **Scope**: First pass, code-grounded against the live `startd8-sdk` tree (this is a fresh worktree
  branch, `src/startd8/manifest_suggester/` does not exist yet). Verified against
  `manifest_extraction/extractors.py`, `stakeholder_panel/panel.py`/`persona.py`/`routing.py`,
  `wireframe/inputs.py`, `backend_codegen/{pages,htmx}_generator.py`. Addresses the 5 focus-file asks
  first, then standard S-suggestions across the 7 areas (all at 0 accepted — two-tier priority mode).

**Focus-file asks**

**Ask 1 — The composite-not-CRUD scope**
- **Summary answer:** Yes — the premise is confirmed by the live code.
- **Rationale:** `backend_codegen/pages_generator.py:1` reads "Content-pages generator (Cap 1) — owned,
  **non-entity** pages from a `pages.yaml` manifest," and `backend_codegen/htmx_generator.py:5` reads
  "**CRUD** + inline validation (list / detail / create+edit form / delete...)" — confirming entity CRUD
  is generated straight from the schema, with no manifest involved. `pages.yaml`/`views.yaml` genuinely
  have no CRUD-page shape to duplicate.
- **Assumptions/conditions:** None — this is settled by the docstrings of the generators themselves, not
  an inference.
- **Suggested improvements:** None needed on this point; the plan's §"Planning discoveries" row citing
  `pages_generator.py:1` is accurate and can be cited with confidence in FR-MS-1.

**Ask 2 — Schema-grounding vs the extractor round-trip**
- **Summary answer:** Partial — both gates are needed, but the plan's grounding guard (Step 2) is
  currently scoped too narrowly to catch everything the real extractor will reject.
- **Rationale:** `manifest_extraction/extractors.py:extract_views` rejects far more than "unknown
  entity": an unrecognized `Kind` (outside `{dashboard, board, workspace, detail-compose,
  export-package, import-flow, computed-panel}` — 7 values, not the 3 in OQ-1), a `board` without
  `Group by:`, a `Shows: A→B` pair with **no derived join model** between A and B (fk-unavailable —
  never guessed), and a `Panel:` line naming a field not on the `Root` entity, are all real, disjoint
  round-trip rejection reasons. A candidate that passes a naive "entities_referenced ⊆ declared
  entities" guard (Step 2 as scoped) can still fail the round-trip on any of these. So yes, a
  role-drafted composite can pass the schema guard yet fail the extractor.
- **Assumptions/conditions:** Assumes Step 2's `grounding.py` is implemented literally as described
  ("every `entities_referenced` must be a declared entity/field") and nothing more.
- **Suggested improvements:** Either (a) broaden `ground()` to also check the Kind-specific structural
  prerequisites it can cheaply verify without re-implementing the extractor (Kind ∈ the real vocabulary;
  `board` candidates carry a `Group by` referencing a Root field; any `Shows:` pair has an actual derived
  join), or (b) explicitly document in FR-MS-4 that the grounding guard is a **necessary, not sufficient**
  pre-filter and that the extractor round-trip is the authoritative, final gate — so a "guard passed,
  round-trip failed" outcome is expected behavior, not a bug, and Step 7's test suite should include at
  least one case per rejection class above.

**Ask 3 — Panel-infra reuse boundary**
- **Summary answer:** Partial — `routing.route`/`roster` are cleanly generic and reusable as described,
  but the plan's proposed call shape (`Persona.ask(question, value_path)`) is the wrong reuse surface.
- **Rationale:** `stakeholder_panel/persona.py:Persona.ask(question, *, value_path="")` is an **instance
  method on one already-bound persona** with no cost tracking, transcript persistence, budget preflight,
  or OTel span — those all live one layer up, in `stakeholder_panel/panel.py:StakeholderPanel.ask(role_id,
  question, *, value_path="")`, which resolves `role_id → Persona` internally and wraps the call with
  `panel.ask` spans, `_record_cost`, and transcript append. The sibling `recommend_inputs(package_root,
  panel, ...)` (the exact precedent this project should mirror) takes a live `panel` and calls
  `panel.ask(owner, drafting_prompt, value_path=slot.value_path)` — never constructs or touches a bare
  `Persona`.
- **Assumptions/conditions:** Assumes `suggest.py` needs the same cost/telemetry/transcript guarantees
  every other paid panel surface gets (a reasonable assumption per NR-KIR-4-style "no parallel panel
  construct" discipline elsewhere in this codebase).
- **Suggested improvements:** Change Step 3's reuse target from `Persona.ask` to `StakeholderPanel.ask`
  (i.e. `suggest_screens(package_root, panel, facts, cap=...)` mirroring `recommend_inputs`'s signature);
  `routing.route(briefs, value_path)` still resolves the owning `role_id` first, then `panel.ask(role_id,
  ...)` is the call. This also means `suggest.py` needs the **live panel** as an argument, not a
  standalone `Persona`, which the plan should make explicit in its module-layout table.

**Ask 4 — The `manifest` apply seam**
- **Summary answer:** Yes, with one important correction to how the `$0` baseline must be constructed.
- **Rationale:** `kickoff_experience/proposals.py:_apply_manifest` takes prose-only `source`, extracts via
  `manifest_extraction.extract.extract_manifests`, and maps each yielded manifest to `wireframe/
  inputs.py:CONVENTION_PATHS["pages"]`/`["views"]` (`prisma/pages.yaml`/`prisma/views.yaml`) — exactly as
  OQ-2 describes, confirmed. **However**, `extract_views` resolves exactly **one** `Root:` entity per
  view (`view["root"] = root`, singular) — the plan's FR-MS-1 phrase "a dashboard view over the **primary
  entities**" (plural) cannot mean multiple independent roots in one view. Additional entities can only
  appear via `Shows: A→B` (relations, requiring an actual derived join/FK between A and B) or `counts of
  <entity>` (aggregates, same join requirement) — never as a second free-standing root.
- **Assumptions/conditions:** None beyond the extractor code read above.
- **Suggested improvements:** Reword Step 1's `baseline_views` contract to: pick **one** root entity
  (e.g. the entity with the most inbound/outbound relations, or the first non-join model in schema
  declaration order) and emit `Shows:`/`counts of` lines **only** for other entities that
  `EntityGraph.join_between` actually connects to the chosen root — otherwise the `$0` baseline's own
  default output could fail the round-trip gate it exists to satisfy trivially. This is worth a
  dedicated Step-7 test: "a schema with 3 unrelated entities produces a baseline dashboard referencing
  only the joined subset, not all three."

**Ask 5 — Value vs cost**
- **Summary answer:** Depends — the `$0` baseline is worth keeping only if Ask 4's one-root correction
  is applied; a baseline that silently fails its own round-trip (Ask 4) would deliver negative value
  (a broken default on every fresh schema) rather than the "the whole value is in the paid pass"
  fallback framing implies.
- **Rationale:** A single, always-correct `$0` starter composite meaningfully de-risks first use (it
  proves the manifest path end-to-end for a project owner before they ever spend on the role pass), but
  only if it is guaranteed groundable *and* round-trip-clean for an arbitrary schema — which, per Ask 4,
  requires the join-awareness the current plan text doesn't specify.
- **Assumptions/conditions:** If the join-awareness fix (Ask 4) is out of scope for v1, the `$0` baseline
  should degrade to "one root entity, no relations/aggregates at all" (always round-trip-safe, lower
  value) rather than attempting unowned `Shows:`/`counts of` lines.
- **Suggested improvements:** Keep the `$0` baseline, but make the fallback-to-relation-free-dashboard
  behavior explicit in FR-MS-1/Step 1 as the safe default when no join exists between candidate entities.

**Standard suggestions**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Interfaces | high | Change Step 3's reuse target from a bare `stakeholder_panel.persona.Persona` to the live `StakeholderPanel` (mirror `recommend_inputs(package_root, panel, ...)`'s signature exactly: `suggest_screens(package_root, panel, facts, *, cap=None)`), calling `panel.ask(role_id, drafting_prompt, value_path=...)` after `routing.route()` resolves `role_id`. | See Ask 3 above — `Persona.ask` bypasses cost tracking, transcript persistence, budget preflight, and OTel spans that only `StakeholderPanel` provides; using it directly would create a second, uninstrumented paid-call path. | Plan §"Approach & step map", Step 3 | A test asserts `suggest_screens` never imports `stakeholder_panel.persona.Persona` directly; cost/telemetry assertions parallel `recommend_inputs`'s test suite. |
| R1-S2 | Data | high | Rewrite Step 1's `baseline_views` contract per Ask 4: pick one root entity; only add `Shows:`/`counts of` lines for entities the schema's derived join graph actually connects to the root; degrade to a relation-free dashboard when no join exists. | Without this, the `$0` baseline can emit a candidate that fails its own round-trip on the very first fresh project (Ask 4/Ask 5). | Plan §"Approach & step map", Step 1 | Step 7 test: 3-entity schema with only 2 joined → baseline references exactly those 2, never the third. |
| R1-S3 | Validation | medium | Broaden Step 2's `ground()` (or explicitly scope it as partial) per Ask 2: check Kind-vocabulary membership and Kind-specific required keys (e.g. `board` → `Group by`) before handing off to the round-trip, or document the two-gate division of labor explicitly so a "guard passed / round-trip failed" outcome isn't read as a bug. | A grounding guard that only checks entity existence gives a false sense of completeness; several real, cheap-to-detect-early rejection classes (bad Kind, missing `Group by`, ungrounded `Shows:` pair) currently only surface at the round-trip, one layer later than necessary. | Plan §"Approach & step map", Step 2; §7 Validation Strategy | One test per rejection class listed in Ask 2's rationale. |
| R1-S4 | Ops | medium | Wrap `suggest.py`'s paid pass in a parent OTel span analogous to `stakeholder.recommend_pass` (aggregating cost/candidates-enumerated/candidates-drafted), reusing `stakeholder_panel.telemetry.span` directly rather than inventing a new span helper. | Direct, already-proven precedent (`recommend.py`'s `stakeholder.recommend_pass` + `_stamp_span`); skipping it leaves the suggester's paid calls without the same cost/scale rollup every other panel-adjacent paid surface has. | Plan §"Approach & step map", Step 3 | Trace inspection: `panel.ask` spans nest under a `screens.suggest_pass`-style parent span. |
| R1-S5 | Architecture | medium | Promote the `ProposalStore` shape from `stakeholder_panel/proposals.py` (own subdir, atomic `mkstemp`+`os.replace`, `sort_keys=True, indent=2`, `latest_session`/`session_ids`/`gc_stale_proposals`, `_safe_session_component` path-traversal guard) as the reference implementation for Step 5's `store.py`, rather than designing a new staging store from scratch. | Low-effort/high-value (Lens 1): every hard edge case here (atomicity, diffability, ambiguous-`--session`, GC, path-traversal in a session id) is already solved and CRP-hardened through 4 rounds in the sibling `STAKEHOLDER_INPUT_RECOMMENDATIONS` feature (see that plan's R5-S4, filed in this same review pass). | Plan §"Approach & step map", Step 5 | `store.py`'s on-disk shape (dir layout, permissions, serialization) is asserted to match `ProposalStore`'s contract in a shared test helper. |
| R1-S6 | Security | low | Have `store.py` mirror `ProposalStore`'s at-rest posture — restrictive directory permissions (`0700`) plus an atomic tmp+replace write — rather than a plain `json.dump`, since a `ScreenCandidate`'s drafted prose could echo brief/project context the persona was given. | The staged screens file is functionally identical in sensitivity to the panel's staged recommendations (both hold LLM-drafted content tied to project internals); there's no reason to give it a weaker at-rest posture just because it's a new module. | Plan §"Approach & step map", Step 5 | File-permission assertion in the same test that covers R1-S5. |
| R1-S7 | Risks | medium | Clarify FR-MS-3's dedupe identity: match by the extractor-derived slug (`nfkd_kebab` normalization used by `extract_pages`/`extract_views`'s `ident`), not by raw candidate `name` string equality — two names differing only in case/punctuation currently collide at the extractor/route level but wouldn't be caught by a naive name-equality dedupe. | Without slug-normalized dedupe, the suggester could propose a "screen" that's a near-duplicate of an existing one by name but collides once both are extracted/routed, discovered only at apply time instead of at dedupe time (Step 4). | Plan §"Approach & step map", Step 4 | Test: an existing `views.yaml` has `Signup Funnel`; a candidate named `signup-funnel` (or `SIGNUP FUNNEL`) is dropped by dedupe, not just at apply. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- None — first round, Appendix C had no prior entries.

## Requirements Coverage Matrix — R1

| Requirement Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-MS-1 (Schema-grounded composite baseline) | Step 1 | Partial | Single-root + join-gated relations not yet specified (R1-S2/Ask 4). |
| FR-MS-2 (Role-informed suggestions) | Step 3 | Partial | Reuse target should be `panel.ask`, not `Persona.ask` (R1-S1/Ask 3). |
| FR-MS-3 (Only suggest what's missing) | Step 4 | Partial | Dedupe identity (slug vs raw name) unspecified (R1-S7). |
| FR-MS-4 (Grounding guard) | Step 2 | Partial | Guard scoped to entity-existence only; misses Kind-specific round-trip prerequisites (R1-S3/Ask 2). |
| FR-MS-5 (Round-trip-gated apply) | Step 5, §7 | Full | Confirmed against `_apply_manifest`/`CONVENTION_PATHS` (Ask 4). |
| FR-MS-6 (Provenance) | Step 5 | Full | — |
| FR-MS-7 (draft → review → approve loop) | Step 5 | Partial | Staging store (`store.py`) should mirror `ProposalStore`'s proven shape rather than being designed fresh (R1-S5/R1-S6). |
| FR-MS-8 (Surfaces the screens gap) | Step 6 | Full | — |

#### Review Round R2 — claude-sonnet-5 — 2026-07-03 02:00:00 UTC

- **Reviewer**: claude-sonnet-5
- **Date**: 2026-07-03 02:00:00 UTC
- **Scope**: Second, adversarial pass. R1 verified per-candidate correctness (grounding, entity
  resolution, panel reuse). This round traces what happens when **more than one** candidate is approved
  over time against the same project — the exact incremental UX FR-MS-7/FR-MS-3 describe — by reading
  `manifest_extraction/extract.py:extract_manifests` and `kickoff_experience/proposals.py:_apply_manifest`
  end to end.

**Executive summary**
- Found a **critical, load-bearing gap**: the `manifest` proposal kind's apply path is a **whole-file
  replace** (`ACTION_NEW`/`ACTION_OVERWRITE` of the *entire* `views.yaml`/`pages.yaml`), derived purely
  from the one candidate's prose passed as `source` — there is **no merge with the existing YAML** and
  **no reverse renderer** that turns the live `views.yaml`/`pages.yaml` back into authoring prose. Approving
  a second screen after a first has already landed (or after any hand-authored screen already exists —
  precisely the common case FR-MS-3's dedupe logic assumes) will either refuse (`would_clobber`) or, if
  pushed through with `replace=true`, **silently destroy every previously-approved/hand-authored screen**.
- This single-candidate-at-a-time UX (FR-MS-7: "approve/reject → a `manifest` proposal per screen") is
  therefore **incompatible with the apply seam FR-MS-5 commits to reusing**, as currently scoped — and it
  is the very first realistic multi-screen flow the whole feature exists to support.
- A second, related finding: Step 1's proposed `EntityFacts` should not be a new parallel structure — it
  should be (or wrap) `manifest_extraction.entities.EntityGraph` directly, since that is the *exact*
  object the round-trip extractor uses internally for `resolve_entity`/`join_between` (needed for both
  Ask 2's guard-completeness gap and Ask 4's join-gating fix from R1). Building on the same object
  guarantees identical resolution semantics by construction rather than by convention.
- A third finding: `EntityGraph.resolve_entity`'s matching is squash+plural-normalized against the
  *exact* declared entity name — a persona drafting prompt that doesn't hand the persona the literal
  entity name strings risks spurious grounding failures on well-intentioned natural-language references.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Risks | critical | Specify an explicit accumulation strategy for the apply seam before build: either (a) the suggester's `store.py`/CLI becomes the keeper of a running authoring-prose document (conventionally persisted, e.g. `docs/kickoff/inputs/screens-authoring.md`) that accumulates every approved candidate's prose block, and every `approve` re-emits the **whole accumulated document** as `source` with `replace=true` against the current `views.yaml`/`pages.yaml`; or (b) build a "decompile" renderer (`views.yaml`/`pages.yaml` → authoring prose) so each `approve` can synthesize the full document (existing entries' prose + the new candidate's prose) on the fly. Verified: `kickoff_experience/proposals.py:_apply_manifest` derives its entire write purely from the proposal's `source` text via `extract_manifests({label: source}, ...)` — there is no reference to, or merge with, what's already on disk; and `manifest_extraction/extract.py`/`extractors.py` contain no YAML→prose reverse renderer anywhere in the tree. | Without one of these, the second (and every subsequent) approved screen either fails outright (`would_clobber`, since `views.yaml`/`pages.yaml` already exists from the first approval) or — if a naive implementation reaches for `replace=true` to "just make it work" — silently deletes every prior screen on each new approval. This is not an edge case; it is the *first* multi-screen approval in the *first* realistic session. | Plan §"Approach & step map", Step 5 ("draft → review → approve") and §7 "Validation Strategy" | A test that approves 2 candidates in sequence against an initially-empty `views.yaml` and asserts **both** views are present in the final file after the second `approve` (not just the second, clobbering the first). |
| R2-S2 | Architecture | high | Define Step 1's `EntityFacts` as a thin wrapper over (or a direct alias for) `manifest_extraction.entities.EntityGraph`, built the same way the round-trip extractor builds it internally (`graph_from_prisma(parse_prisma_schema(schema_text))`) — not a new parallel type. | Both the grounding guard (Step 2, Ask 2/R1-S3) and the join-gated `$0` baseline (Step 1, Ask 4/R1-S2) need exactly `EntityGraph.resolve_entity`/`.join_between`; reusing the literal object the extractor itself uses guarantees the guard's "grounded" verdict and the extractor's "round-trips" verdict can never diverge due to two independent entity-matching implementations drifting apart. | Plan §"Approach & step map", Step 1 (`schema_entities`) | A single shared fixture schema is fed through both `schema_entities` (suggester) and the extractor's own graph-build path; assert `resolve_entity`/`join_between` results are identical (trivially true if it's the same object, but pins the contract). |
| R2-S3 | Validation | medium | The drafting prompt template (Step 3, not yet specified) must hand the persona the **literal, exact declared entity name strings** (from `EntityFacts`/`EntityGraph.entities`) and instruct it to reference them verbatim in `Root:`/`Shows:` lines — not describe entities in free natural language. | `EntityGraph.resolve_entity` only normalizes case/plurality/non-letter-squashing against the *exact* declared name; a persona-drafted reference like "the customer's profile" for a declared entity `Customer` will not resolve, and would be rejected by the grounding guard for a reason that has nothing to do with genuine ungroundedness — it's a prompt-design gap, not a persona error. | Plan §"Approach & step map", Step 3 (the drafting prompt) | A test: a fixture entity `CustomerProfile`; a prompt-simulated persona reply using the exact string `CustomerProfile` grounds successfully, while a hypothetical free-form paraphrase would not — used to justify requiring literal names in the prompt contract. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R1-S2/R1-S5: both still stand and are complementary to this round's findings rather than superseded — R1-S2 (join-gated single-root baseline) and R1-S5 (reuse the `ProposalStore` shape) remain independently necessary regardless of how the accumulation gap (R2-S1) is resolved.

## Requirements Coverage Matrix — R2

| Requirement Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-MS-5 (Round-trip-gated apply via `manifest`) | Step 5, §7 | Partial | No accumulation/merge story for a second+ approved screen against an existing manifest (R2-S1) — this was marked Full in R1's matrix, revised here after tracing the multi-approval flow. |
| FR-MS-7 (draft → review → approve loop) | Step 5 | Partial | Per-candidate approval is incompatible with the whole-file-replace apply seam as scoped (R2-S1). |
| FR-MS-1 / FR-MS-4 (schema grounding) | Step 1, 2 | Partial | `EntityFacts` should wrap the extractor's own `EntityGraph`, not a parallel type (R2-S2); drafting prompt must supply literal entity names (R2-S3). |
| (all other sections) | — | Unchanged | See R1's matrix for FR-MS-2/3/6/8. |

#### Review Round R3 — claude-sonnet-5 — 2026-07-03 02:15:00 UTC

- **Reviewer**: claude-sonnet-5
- **Date**: 2026-07-03 02:15:00 UTC
- **Scope**: Third pass (explicit user request for depth). Traced how `parse_sections`
  (`manifest_extraction/grammar.py`) actually delimits sections — purely by any line matching
  `^(#{2,4})\s+` — to check whether free-text content inside a candidate's prose could smuggle in
  additional, unreviewed manifest entries. This mirrors the companion Stakeholder Input Recommendations
  review's R7 finding (unsanitized LLM free text meeting a structurally-significant parser) applied to
  this project's prose/markdown surface instead of that project's YAML-splice surface.

**Executive summary**
- **Found a security-relevant prose-injection gap**: `parse_sections` creates a new section boundary
  for **any** line starting with `##`/`###`/`####` followed by a space, with zero awareness of whether
  that line is "supposed to be" a heading or just body text. `extract_views` picks up every section whose
  title starts with `"view:"`. If a role persona's **free-text** field (a rationale, an entity
  description, anything not itself constrained to a closed vocabulary) is echoed into the candidate's
  prose and happens to contain a line matching that pattern (accidentally, or via injected content in the
  project brief/schema the persona was given), the assembled `source` text handed to `_apply_manifest`
  could contain **additional `view:`/`### Form:`/etc. sections the human never saw or approved** as part
  of the one candidate they reviewed and approved.
- This is a direct violation of this project's own **P4** ("Propose, then human-apply... the human
  approves each screen") and **FR-MS-6** ("a suggested screen carries a provenance marker... the human
  approval is the sole promotion gate") — the promotion gate is only meaningful if what gets applied is
  what got shown.
- No prior round (R1/R2) examined the prose-assembly step itself; R1/R2 focused on entity-grounding
  correctness and the apply seam's file-level semantics, not the *section-boundary* safety of the
  markdown the suggester itself constructs.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-S1 | Security | critical | Before any `ScreenCandidate`'s prose is (a) rendered for `review` or (b) included in a `manifest` proposal's `source`, scan every free-text field (rationale, any persona-authored description) for a line matching `manifest_extraction.grammar._HEADING_RE`'s pattern (`^#{2,4}\s`) and either reject the candidate outright (safest) or escape the line (e.g. prefix with a zero-width marker or demote to a blockquote) so it can never be interpreted as a new section boundary. Verified: `parse_sections` (`manifest_extraction/grammar.py:61`) is a pure line-scanner with no nesting/quoting awareness — any `##`/`###`/`####`-prefixed line anywhere in the assembled document becomes a new `Section`, and `extract_views` (`extractors.py:108`) picks up every section titled `view:*` regardless of where in the document it appeared. | Without this, a single "approved" candidate could smuggle in extra manifest entries never shown to the human reviewer — the exact failure mode P4/FR-MS-6's "human approval is the sole promotion gate" language exists to prevent. | Plan §"Approach & step map", Step 3 (drafting) and Step 5 (the `manifest` proposal `source`) | A test: a persona reply's rationale field contains the literal text `"...\n### view: Injected\nKind: dashboard\nRoot: User"`; assert the resulting candidate is rejected (or the injected heading is neutralized) **before** it ever reaches `_apply_manifest`, and that `extract_manifests` on the final `source` yields only the one intended view. |
| R3-S2 | Validation | high | `panel review`'s `$0` render (Step 5) must render the **literal bytes** of the `source` text that would be submitted on approval — not a summarized/re-derived preview — so a human reviewing "one screen" is actually looking at everything that will be extracted, including any injected sections R3-S1 didn't catch. | A review surface that shows a friendly summary ("Dashboard over User, Order") instead of the literal prose risks the human approving something they never actually read byte-for-byte — the same "review renders the gap, not just the fill" anti-anchoring discipline the sibling Stakeholder Input Recommendations feature already applies (FR-KIR-9) should apply here too. | Plan §"Approach & step map", Step 5 (`review`) | A review-output snapshot test: the rendered text for a candidate is byte-identical to (or a clearly-delimited superset that includes) the prose that will become the `manifest` proposal's `source`. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R2-S1: still stands and is now doubly important — any accumulation/merge strategy adopted for R2-S1 must ALSO pass through the R3-S1 sanitization before assembling the merged document's `source`, or the injection risk compounds across every subsequent approval.

## Requirements Coverage Matrix — R3

| Requirement Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-MS-6 (Provenance, human approval is sole promotion gate) | Step 5 | Partial | No sanitization/verbatim-review guarantee against heading-injection in free-text fields (R3-S1/R3-S2) — this was marked Full in R1's matrix; revised here. |
| FR-MS-7 (draft → review → approve loop) | Step 5 | Partial | Compounds with R2-S1's accumulation gap: any merged/accumulated document must also pass R3-S1's sanitization (see Endorsements). |
| (all other sections) | — | Unchanged | See R2's matrix. |

#### Review Round R4 — claude-sonnet-5 — 2026-07-03 02:20:00 UTC

- **Reviewer**: claude-sonnet-5
- **Date**: 2026-07-03 02:20:00 UTC
- **Scope**: Fourth pass. Since this project has no code yet, focused on lessons the sibling
  **Stakeholder Input Recommendations** feature already paid for through 7 CRP rounds (budget-preflight
  ordering, staging-aware re-spend guard) that this plan's Step 3 doesn't yet inherit explicitly, plus a
  distinction between two dedup axes (against the live manifest vs. against a prior pending session) the
  plan currently conflates.

**Executive summary**
- The sibling Teian feature learned, the hard way (R3-S1, 4 CRP rounds ago), that **budget preflight
  must run after routing/filtering**, not before — preflighting the raw candidate count overestimates
  cost and can falsely deny an affordable run. This plan's Step 3 doesn't state an equivalent ordering
  for the role-informed pass, risking rediscovery of the exact same bug this codebase has already fixed
  once.
- Distinct from FR-MS-3's dedupe (**against the live, already-applied `views.yaml`/`pages.yaml`**),
  nothing in the plan dedupes a role-drafted candidate against a **still-pending, not-yet-approved**
  suggestion from a prior `suggest --roles` run — running `suggest --roles` twice before approving
  anything would draft (and pay for) the same screen twice, the exact Mottainai violation FR-KIR-12/R2-S2
  fixed on the sibling project's `recommend` pass.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-S1 | Ops | high | Specify that the role-informed pass's budget preflight (Step 3) runs **after** dedup (Step 4) and routing resolution — mirroring the sibling `STAKEHOLDER_INPUT_RECOMMENDATIONS_PLAN.md`'s R3-S1 fix ("preflight the resolved, capped set — *after* resolution so an un-owned domain never inflates the count"). Currently Step 3/4 are listed in an order (drafting, then dedupe) that, if implemented literally, would preflight against the pre-dedup candidate count and overestimate cost. | This is a lesson the codebase already paid for once (4 CRP rounds on the sibling feature); inheriting it explicitly here is a direct, near-zero-cost application of Lens 3 (platform leverage) rather than re-discovering the same bug through this project's own future CRP cycle. | Plan §"Approach & step map", reorder/annotate Steps 3-4 | A test: N candidates drafted, M of them already exist in the live manifest (deduped), cap=M+1; assert the preflight count is the post-dedup count, not N. |
| R4-S2 | Risks | medium | Add a staging-aware re-spend guard to the role-informed pass, distinct from FR-MS-3's live-manifest dedupe: before drafting, check the **latest pending session** in `store.py` (once it exists, mirroring `ProposalStore`) for a candidate with the same derived slug, and skip it (no LLM call) unless a `--redraft`-equivalent flag is passed. | FR-MS-3 only dedupes against what's **already applied**; nothing currently prevents a second `suggest --roles` invocation (before the first batch is ever approved) from drafting — and paying for — the same screen again. This is the exact Mottainai gap FR-KIR-12/R2-S2 closed on the sibling `recommend` pass, on a different axis (pending-session dedup vs. live-manifest dedup). | Plan §"Approach & step map", Step 3 (role-informed drafting) and Step 4 (dedupe) — the two dedup axes should be documented side by side so a reader doesn't conflate them | A test: run `suggest --roles` twice without approving anything in between; assert the second run makes 0 paid calls for candidates already pending from the first run. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R3-S1: still stands and is complementary — the sanitization gap (R3-S1) and the re-spend/preflight-ordering gaps (this round) are independent failure modes in the same drafting pass.

## Requirements Coverage Matrix — R4

| Requirement Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-MS-2 (Role-informed suggestions) | Step 3 | Partial | Budget-preflight ordering not specified (R4-S1); no staging-level re-spend guard (R4-S2) — this was marked Partial in R1's matrix for a different reason (panel reuse target), now also partial on this axis. |
| FR-MS-3 (Only suggest what's missing) | Step 4 | Partial | Dedupes only against the live manifest, not against a prior session's pending candidates (R4-S2) — a second, distinct dedup axis this requirement doesn't currently name. |
| (all other sections) | — | Unchanged | See R3's matrix. |

