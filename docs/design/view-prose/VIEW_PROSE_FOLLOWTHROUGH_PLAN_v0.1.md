# View Prose Follow-Through — Implementation Plan (reflective loop Phase 2)

**Version:** v0.1 (post-exploration; feeds the v0.2 reflective update of the requirements)
**Date:** 2026-06-12
**Status:** Plan — ready to reflect back onto the requirements
**Pairs with (the "what"):** `VIEW_PROSE_FOLLOWTHROUGH_REQUIREMENTS_v0.1.md` (18 FRs across groups A-F).
All citations are from a read of SDK `main` @ `0e8d08fb`.

> **Reading order.** §0 is the discoveries that change the requirements (the centerpiece — the loop
> working). §1 is the per-group implementation shape (file:line-grounded). §2 is the reshaped
> scope/sequencing. §3 is what flows back to v0.2.

---

## 0. Discoveries (what planning revealed — these reshape the requirements)

| # | The requirements assumed (v0.1) | Planning revealed | Impact |
|---|---|---|---|
| **D1** | FR-FMT-1 is "add a View-copy section to the template" — a docs edit | **The requirements doc is a deterministic ($0, no-LLM) manifest SOURCE.** `manifest_extraction/extract.py` ingests it and emits **6 manifests** (pages/app/ai_passes/human_inputs/views/completeness) + schema — but **NOT `view_prose.yaml`** (and not `display.yaml`). The consumer (`parse_view_prose`) exists; the **producer (extractor) does not** — the SDK is half-wired. | **FR-FMT-1 is PROMOTED** from a doc edit to a real codegen capability: *author view copy in the reqs doc → deterministically generate `view_prose.yaml`*. Becomes its own FR group (G). |
| **D2** | (not seen) | **`Empty state:` is ALREADY authored** in every `### View:` block of the template, but `parse_views` has no home for it → it maps to **`not_extracted(generator-gap)`** (`extractors.py:241-245`, `KICKOFF_AUTHORING_CONTRACT.md:171`). Meanwhile view_prose's `empty` key + renderer now exist. | **NEW quick win, invisible before planning:** connect the existing-but-ignored `Empty state:` authoring → `view_prose.yaml` `empty:`. Both ends already exist; only the extractor connects them. |
| **D3** | (not seen) | **The extraction emits 6 of the 8 manifests the cascade consumes** — `view_prose.yaml` AND `display.yaml` are both un-derived (same gap class). | New theme: **manifest-extraction parity** — the derivation should produce every manifest the $0 cascade reads. display.yaml is a sibling of the view_prose extraction. |
| **D4** | Group A "skip-hook threading" needs building | The backend provider **already has** `_read_anchored()` / `_read_manifest()` / `_read_human_inputs()` helpers — **but `is_in_sync()` doesn't call them** (passes schema only, `provider.py:29-35`). `check_drift` already has the full kind-routing + signature. | **FR-DRC-3 is smaller than feared** — "wire up helpers that already exist," not new plumbing. Strengthens the "small thread-through" verdict. |
| **D5** | FR-DRC-2 = "add flow kinds to `_FORMS_KINDS`" | Flow kinds (`fastapi-flow`/`flow-shell`) are in **no** kind-set AND **no** renderer map; a kind needs **both** to be drift-checkable. Flows are semantically distinct from forms post-create. | FR-DRC-2 reframed as a **new `_FLOWS_KINDS` family** (kind-set + `_check_flows_drift` + `_flows_renderers`), parallel to forms — slightly bigger but cleaner than overloading `_FORMS_KINDS`. |
| **D6** | FR-DRC-5 regression lock spans the backend kinds | There are **5 deterministic providers** (backend kind-routed; frontend/scaffold/polish marker-or-path; view path-suffix). The lock must span **all** of them. The implicit kind→inputs map (the `_*_KINDS` sets) made **explicit** (FR-DRC-1's `KIND_TO_INPUTS`) is what makes both the skip-hook threading AND the lock possible. | FR-DRC-1 is **load-bearing for 3/5** (not optional); FR-DRC-5 widened to all providers. |
| **D7** | FR-FMT-2 (codify the reflective lifecycle) might be a parser concern | **Zero** machine consumption — `manifest_extraction/*` + `grammar.py` have **no** refs to "Appendix"/"Planning Insights"/"version lineage"/"what changed"; format rule 5 ignores any non-anchored section. | **FR-FMT-2 NARROWS** to a pure format-doc edit (human convention) — lower risk, fully decoupled from FR-FMT-1. |
| **D8** | FR-DP-2 = extract a shared untracked-fragment primitive | The three mechanisms are **intentionally divergent**: pages/view-prose are **generate-time** untracked fragments; **AI prompts are RUNTIME-loaded** (read from disk by the generated harness, not a generate-time fragment at all — `ai_layer.py:695-700`). Timing/format/discovery all differ. | **FR-DP-2 DROPPED** (extraction not worth it / partly impossible — AI-prompt isn't the same pattern). Folds into FR-DP-1 as "document the pattern + note the runtime-binding variant." |
| **D9** | FR-WCI-2 (content-completeness rollup) is a quick win bundled with FR-WCI-1 | FR-WCI-1 (add view_prose to the catalog + per-view chrome status) **is** quick — the `Status` model + `_yaml_state` pattern exist (`plan.py:45-50`). But the **rollup** has no existing per-surface aggregation; it needs a new `ContentCoverageStats` + a `--json` schema bump = **MEDIUM**. | **Split FR-WCI-1 (quick) from FR-WCI-2 (medium).** |

**Net:** > a third of the v0.1 FRs are materially reshaped — the loop working as intended. The single
biggest shift: the "template/format" bucket is not cosmetic — the reqs doc is a deterministic manifest
*compiler*, and its two newest target manifests aren't compiled yet. That converts FR-FMT-1 into a
high-value capability with an **immediate payoff** (the already-authored `Empty state:` dead-end lights up).

---

## 1. Implementation shape (per group, file:line-grounded)

### Group A — Drift-recognition completeness (the small thread-through)
> **R1 correction (S1/S5):** only the **backend** provider has kinds; the other 4 are kindless
> (frontend=schema-only, scaffold=marker+app.yaml, polish=marker+path-suffix, view=marker+whole-set). So
> `KIND_TO_INPUTS` is **backend-only**; the 4 kindless providers carry a **provider-level `declared_inputs`**;
> the lock enumerates from each provider's own recognition surface (non-empty per provider).
- **FR-DRC-1 — explicit `KIND_TO_INPUTS` (backend) + per-provider `declared_inputs` (the other 4).** Add a
  module-level dict in `backend_codegen/drift.py` mapping each backend kind → its manifests (`schema` always;
  `+forms` for `_FORMS_KINDS`/`_FLOWS_KINDS`; `+pages` for `_PAGES_KINDS`; `+ai_passes,+human_inputs` for
  `_AI_KINDS`; `schema`-only for `_renderers()` + `_SETTINGS_KINDS`). For the kindless providers, expose a
  `declared_inputs` on each provider. Fail-closed: an unknown backend kind → not-in-sync (`drift.py:600-606`).
  **Load-bearing for FR-DRC-3 and FR-DRC-5.**
- **FR-DRC-2 — `_FLOWS_KINDS` family (routing order, S7).** New `_FLOWS_KINDS = {"fastapi-flow","flow-shell"}`
  + a `_flows_renderers()` (`render_flow_router`/`render_flow_shell` from `flow_generator.py:30/112`) +
  `_check_flows_drift()` (forms-hash style: schema + views.yaml), **routed in `check_drift` BEFORE the
  `_renderers()` unknown-kind fallthrough** that returns `tampered` (`drift.py:600-606`) — else a valid flows
  file false-flags. *Verify: an unchanged flows app reports `in_sync`, not `tampered`.*
- **FR-DRC-3 — backend `is_in_sync` threads the kind's manifests.** In `backend_codegen/provider.py`,
  `is_in_sync` reads the file's kind (`embedded_artifact_kind`), looks up `KIND_TO_INPUTS`, resolves only
  those manifests via the **existing** `_read_anchored()`/`_read_manifest()`/`_read_human_inputs()`
  (`provider.py:62-101`, currently unused), and `owned_file_in_sync` gains the manifest kwargs to forward
  to `check_drift` — mirroring the CLI (`cli_generate.py:280-290`). **No new plumbing.**
- **FR-DRC-4 — view provider threads `display_text`.** `view_codegen/provider.py:25-37` resolves
  `view_prose.yaml` but not `display.yaml`; add a `_read(suffix="display.yaml", …)` and pass `display_text`
  to `views_in_sync` (which already accepts it). ~3 lines.
- **FR-DRC-5 — regression lock across all 5 providers (per-provider enumeration, S5).** Enumerate from each
  provider's **own** surface — backend `_*_KINDS` ∪ `_renderers()` keys; the 4 kindless providers' `owns()`
  artifact sets — and assert **each is non-empty** (no vacuous pass) and the skip-hook resolves what
  FR-DRC-1 declares. Shared `tests/unit/` artifact if Group A is carved out (R1-F10). Fails when a future
  kind/artifact is added without wiring.

### Group G — View-copy extraction (the promoted FR-FMT-1; D1/D2/D3)
- **FR-VCE-1 — `extract_view_prose()`.** New extractor in `manifest_extraction/extractors.py` parsing
  per-view copy keys from each `### View:` block (the block already uses the `- Key: value` grammar,
  `grammar.py:129`). Wire into the candidate set (`extract.py:145-158`) and the round-trip table
  (`extract.py:162-175`) calling the **existing** `parse_view_prose(text, known_views=…)`
  (`view_prose.py:59`) so a bad copy block fails loudly at *ingestion* (FR-WPI-4), not at `generate views`.
  **R1-S3 fix: `known_views` ≠ the graph.** `extract.py:161` uses `graph.all_model_names()` (models); there's
  no `all_view_names()`. Source view idents from the extracted **`views.yaml` candidate** (views before
  view_prose) or add `Graph.all_view_names()` — ordering alone won't supply them. Honor the renderer's
  escaping contract (R1-F9: markdown/escaped/whitelist per archetype).
- **FR-VCE-2 — close the `Empty state:` dead-end (the quick win, D2; archetype-filtered, S4).** Route the
  already-authored `Empty state:` line (`extractors.py:241-245`, today `not_extracted`) to `view_prose.yaml`
  `empty:` **only for model-scoped detail-compose views**, and **keep silently dropping it (no error) on
  other archetypes** — else existing reqs docs with `Empty state:` on a board/dashboard would start
  loud-failing (the renderer raises on `empty` off-archetype, `renderers.py:~1853`). The archetype filter
  precedes the route.
- **FR-VCE-3 — per-archetype controlled grammar.** The extractor parses `title`/`intro` (any HTML view),
  `empty` (detail-compose model), `success`/`error`/`controls` (import-flow) — and the **existing renderer
  already rejects archetype-invalid combinations** (`renderers.py:1862-1881`), so validity is enforced
  end-to-end with no new validator.
- **FR-VCE-4 (sibling, D3) — `display.yaml` extraction parity.** The same gap exists for `display.yaml`
  (structure layer). Note it as a parallel item; may be its own increment. Brings the derivation to 8/8
  manifests.

### Group C — Format/template (mostly doc; D7)
- **FR-FMT-1' — the template "View copy" keys** (now the *authoring surface* for Group G): add the per-view
  copy keys to `REQUIREMENTS_TEMPLATE.md`'s `### View:` block + a `[consumed by: extraction →
  view_prose.yaml]` annotation in `REQUIREMENTS_AND_PLAN_FORMAT.md`. (Pairs with FR-VCE-1.)
- **FR-FMT-2 — reflective-loop conventions (pure doc, D7):** add §0 Planning Insights / Appendix A-B-C /
  "what changed" / version-lineage / Implementation-Reflections conventions to the format doc + template
  scaffolds. **No parser** touches these.
- **FR-FMT-3 — Words/Structure rule** + **FR-FMT-4 — `$0`-codegen AC checklist:** format-doc additions.

### Group D — Wireframe + capability index
- **FR-WCI-1 (quick).** Add `"view_prose": "prisma/view_prose.yaml"` to `wireframe/inputs.py:30-38`
  CONVENTION_PATHS; a `_view_prose_state()` parallel to `_yaml_state()`; extend `_views_section()`
  (`plan.py:586-636`) to emit per-view chrome status (authored/raw) using the existing `Status` model
  (`plan.py:45-50`).
- **FR-WCI-2 (medium, split out).** A `ContentCoverageStats` rollup (pages + view-copy + AI prompts) in
  `build_wireframe_plan()` + a `--json` `content_completeness` block (schema-version bump).
- **FR-WCI-3 (quick).** Two capability-index entries (`startd8.codegen.composite_views`,
  `startd8.codegen.view_prose`) matching the 12-field de-facto shape (`startd8.sdk.capabilities.yaml:611`).

### Group B — Assembly-inputs consistency (docs)
- **FR-KIN-1/2/3** — correct the stale `ASSEMBLY_INPUTS.md` view_prose entry; classify it under Words;
  add a template row. Pure docs.

### Group F — Design principle (D8)
- **FR-DP-1 — principle doc** (~2-3 pp, MOTTAINAI/HAYAI structure: principle → why → violations → rules →
  changelog) covering the **generate-time untracked-fragment** pattern (pages + view-prose), and noting
  AI-prompts as a **related runtime-binding variant** (not the same pattern).
- **~~FR-DP-2~~ — DROPPED.** Extraction not worth it (divergent timing/format/discovery; AI-prompt is
  runtime, not a generate-time fragment). Folds into FR-DP-1.

### Group E — Functional quick wins (DEFERRED; thin shape per R1 coverage-matrix Gap)
- **FR-QW-1/2/3** are **opportunistic, lowest-urgency** — no detailed §1 shape is given **by design**. Each
  routes an existing hardcoded literal through the shipped prose-fragment mechanism at the anchors named in
  the requirements (`renderers.py:967/1021/1026/1074`), gated on prose presence (byte-identical absent). They
  are sequenced last (§2 step 6) and may stay deferred; this note closes the trace.

---

## 2. Reshaped scope & sequencing
1. **Group A** (drift-recognition) — small thread-through, fixes silent $0→LLM fallthrough + 3 verified
   bugs. Its own PR. *(FR-DRC-1 first; it unblocks 3+5.)*
2. **Group G** (view-copy extraction) — the high-value unlock; FR-VCE-2 (close `Empty state:`) is the
   cheapest first slice and proves the path. Pairs with FR-FMT-1'.
3. **Group D** (wireframe FR-WCI-1 + capability index FR-WCI-3) — quick wins.
4. **Group C/B/F** (docs) — cheap; FR-FMT-2/3/4, FR-KIN-*, FR-DP-1.
5. **FR-WCI-2** (rollup) + **FR-VCE-4** (display extraction parity) — medium follow-ups.

---

## 3. Reflection → what flows back to the requirements (v0.1 → v0.2)
- **Promote FR-FMT-1 → a new Group G (view-copy extraction)** and reframe the "template" bucket: the reqs
  doc is a deterministic manifest compiler; the win is *author copy → derive `view_prose.yaml` ($0)*.
- **Add the `Empty state:` quick win (FR-VCE-2)** — invisible before planning; both ends already exist.
- **Add the manifest-extraction-parity theme (FR-VCE-4 / display.yaml)** — the derivation emits 6 of 8.
- **Strengthen Group A** framing (plumbing already exists, unused) and reframe FR-DRC-2 as a `_FLOWS_KINDS`
  family; widen FR-DRC-5 to all providers; mark FR-DRC-1 load-bearing.
- **Narrow FR-FMT-2** to pure doc (no parser). **Drop FR-DP-2** (fold into FR-DP-1). **Split FR-WCI-1
  (quick) from FR-WCI-2 (medium).**

---

*v0.1 — Plan from `manifest_extraction/` + `backend_codegen/drift.py` + `wireframe/` exploration at
`0e8d08fb`. Central finding: the requirements doc is a deterministic ($0) manifest compiler that doesn't
yet compile `view_prose.yaml`/`display.yaml`, and an already-authored `Empty state:` field is a dead-end
the shipped view_prose machinery can now light up. Next: apply the §3 reflections to requirements v0.2.*

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
| R1-S1 | KIND_TO_INPUTS backend-only; per-provider mechanism for the 4 kindless | R1 (code-verified) | **Applied.** §1 Group A note + FR-DRC-1 (backend map + provider `declared_inputs`). | 2026-06-12 |
| R1-S2 | Sequencing: behavior-change gate before Group A ships | R1 | **Applied.** Folded into FR-DRC-3 (reqs) + §2; cost-delta gate. | 2026-06-12 |
| R1-S3 | `known_views` source wrong (models not views; no `all_view_names`) | R1 (code-verified) | **Applied.** §1 FR-VCE-1 R1-S3 fix added. | 2026-06-12 |
| R1-S4 | FR-VCE-2 archetype filter before routing | R1 (code-verified) | **Applied.** §1 FR-VCE-2 archetype-filter + silent-drop. | 2026-06-12 |
| R1-S5 | FR-DRC-5 per-provider non-vacuous enumeration | R1 | **Applied.** §1 FR-DRC-5 rewritten. | 2026-06-12 |
| R1-S6 | FR-VCE-4 display.yaml feasibility-table gate | R1 | **Applied.** Reqs FR-VCE-4 gated; plan §2 step 5. | 2026-06-12 |
| R1-S7 | FR-DRC-2 route flows BEFORE the `_renderers()` tampered fallthrough | R1 (code-verified) | **Applied.** §1 FR-DRC-2 routing-order clause. | 2026-06-12 |
| R1-S8 | FR-WCI-1 key by view ident not model | R1 | **Applied.** Reqs FR-WCI-1 keyed by view ident. | 2026-06-12 |
| (matrix Gap) | Group E has no §1 implementation shape | R1 coverage matrix | **Applied.** Thin §1 Group E note (deferred; anchors named). | 2026-06-12 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none — all R1 S-suggestions accepted; the high-severity findings were code-verified at `0e8d08fb`) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8[1m] — 2026-06-12 UTC

- **Reviewer**: claude-opus-4-8[1m]
- **Date**: 2026-06-12 19:05:00 UTC
- **Scope**: Plan review (S-prefix) with code-grounded verification of §1 file:line claims across `backend_codegen/drift.py`+`provider.py`, the 5 deterministic providers, `manifest_extraction/extract.py`+`extractors.py`+`entities.py`, and `view_codegen/{provider,drift,renderers}.py`. Sponsor focus asks answered in the requirements doc's R1 block.

##### Numbered suggestions (S-prefix)

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Architecture | high | §1 Group A / §2: state that the `KIND_TO_INPUTS` dict in `drift.py` covers **only the backend provider**, and that FR-DRC-5's cross-provider lock must source inputs from each provider's own recognition surface, not from this one dict. Add a second mechanism for the 4 kindless providers. | Verified: only backend routes on embedded kind (`drift.py:560-575`); frontend=schema-only, scaffold=marker+app.yaml, polish=marker+path-suffix `_render_for`, view=marker+whole-set (their `provider.py`). The plan's §1 implies one map serves all; it cannot. | §1 "Group A" FR-DRC-1/5 bullets | Lock test enumerates a non-empty input-set per provider from that provider's recognized-artifact set. |
| R1-S2 | Ops | high | §2 sequencing: add an explicit "behavior-change gate" before Group A ships — FR-DRC-3 will re-classify previously-$0-skipped manifest-derived files in existing apps as not-in-sync → LLM (cost shift). Sequence a flag or a one-release announce, given downstream repos track the live branch. | Verified: `is_in_sync`→`owned_file_in_sync(schema_text, content)` is schema-only today (`provider.py:29-35`); threading `forms_text` flips false-skips. MEMORY: 9 downstream repos track the editable SDK. Silent cost shifts are surprising. | §2 step 1 (Group A) | A documented before/after $-delta on a fixture app with a changed `forms:` section; changelog entry present. |
| R1-S3 | Data | high | §1 Group G / FR-VCE-1: correct the implied `known_views` source. The plan says to call `parse_view_prose(text, known_views=…)` in the round-trip, but `extract.py:161` builds `known = graph.all_model_names()` (models, not views) and there is no `all_view_names()` (`entities.py:121`). Specify harvesting view idents from the extracted `views.yaml` candidate or adding `all_view_names()`. | Verified file:line. The round-trip table (`extract.py:162-175`) keys off model names; view_prose needs view names. Without this, FR-VCE-1's loud-fail-at-ingestion guarantee can't be wired. | §1 "Group G" FR-VCE-1 bullet | Round-trip test: view-copy referencing an unknown view fails ingestion; a real view passes. |
| R1-S4 | Risks | high | §1 FR-VCE-2: add the archetype-filter step before routing `Empty state:` → `empty:`. The plan says "Map the already-authored `Empty state:` line … to `view_prose.yaml` `empty:` for model-scoped detail-compose views" but doesn't say what to do with `Empty state:` on OTHER archetypes (today silently dropped). Specify: keep dropping (no error) off-archetype. | Verified: `renderers.py:1859-1864` raises `ValueError` on `empty` for non-model-compose at render time. Blind routing would loud-fail existing reqs docs with board/dashboard `Empty state:`. | §1 "Group G" FR-VCE-2 bullet | Test: board view `Empty state:` → no `empty:`, no error; detail-compose → `empty:`. |
| R1-S5 | Validation | medium | §1 FR-DRC-5 / §2: the regression-lock test is described as enumerating "every owned kind" but 4 providers have no kinds. Specify the test's enumeration adapter per provider and assert each contributes a **non-empty** set, so the lock can't pass vacuously. | A lock that enumerates an empty set for polish/scaffold/frontend/view gives false coverage assurance — the exact failure class FR-DRC-5 exists to prevent. | §1 "Group A" FR-DRC-5 bullet | The lock fails if any provider's enumerated artifact set is empty. |
| R1-S6 | Interfaces | medium | §1 FR-VCE-4: before scheduling display.yaml extraction in Group G, add a planning sub-task to produce a field-derivability table (which display.yaml fields the `### View:` grammar carries vs which — column order, FK label resolution — need new authoring). Gate inclusion on that table. | Sponsor ask 4: display.yaml is structure/bindings, a bigger lift than flat view_prose strings. "8/8 parity" framing hides the asymmetry. The plan already calls it "may be its own increment" — make that conditional explicit. | §1 "Group G" FR-VCE-4 bullet + §2 step 5 | The table exists; if any required field needs new authoring, FR-VCE-4 splits to its own increment. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S7 | Risks | medium | §1 FR-DRC-2 (`_FLOWS_KINDS`): the plan adds `_flows_renderers()` mapping `render_flow_router`/`render_flow_shell` but `check_drift`'s unknown-kind path returns `tampered` (`drift.py:600-606`). Verify that adding a new kind-set WITHOUT also adding its renderer to `_renderers()` (or routing it earlier) doesn't make a valid flows file flagged `tampered` by the fallthrough. State the routing order. | A new kind-set checked before the `_renderers()` fallthrough is fine, but if `_check_flows_drift` is added but a flows kind also leaks to the fallthrough, it false-flags. FR-DRC-1's note "a kind needs both" (kind-set + renderer) is the trap. | §1 "Group A" FR-DRC-2 bullet | Test: an unchanged flows app reports `in_sync` on `generate backend --check` (not `tampered`). |
| R1-S8 | Data | low | §1 FR-WCI-1 / §3: the wireframe `_view_prose_state()` will read per-view chrome status, but per S3/F5 the view-name keyspace for view_prose differs from models. Ensure the wireframe keys view-copy status by **view** ident (matching `_views_section` `plan.py:586-636`), not by model, to avoid a mismatched rollup denominator in FR-WCI-2. | Cross-cutting: the same view-name vs model-name confusion that bites FR-VCE-1 (S3) can produce a wrong wireframe denominator. Catch it once. | §1 "Group D" FR-WCI-1/2 bullets | Wireframe test: a view-copy entry shows status against its view, not a model; rollup denominator = view count. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with): none — R1 is the first round; Appendix A/B/C carry no prior items.

---

## Requirements Coverage Matrix — R1

Maps each requirements FR → plan coverage. Analysis only (not triage). Coverage: Full / Partial / Gap.

| Requirement (FR) | Plan section/task | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-DRC-1 (`KIND_TO_INPUTS` registry) | §1 Group A FR-DRC-1; §0 D6 | Partial | Plan presents one `drift.py` dict as the SSOT but only backend has kinds; no mechanism stated for the 4 kindless providers (R1-S1/F1). |
| FR-DRC-2 (`_FLOWS_KINDS` family) | §1 Group A FR-DRC-2; §0 D5 | Partial | Routing order vs the `_renderers()` unknown-kind `tampered` fallthrough unspecified (R1-S7). |
| FR-DRC-3 (backend skip-hook threads manifests) | §1 Group A FR-DRC-3; §0 D4 | Partial | Correctly scoped as "wire existing helpers" (verified `provider.py:62-101`), but the behavior-change/cost gate for existing apps is absent (R1-S2/F4). |
| FR-DRC-4 (view provider threads `display_text`) | §1 Group A FR-DRC-4 | Full | Verified: view provider passes `view_prose_text` not `display_text` (`provider.py:25-37`); `views_in_sync` accepts `display_text` 5th-positional. ~3 lines as stated. |
| FR-DRC-5 (regression lock, all 5 providers) | §1 Group A FR-DRC-5; §0 D6 | Partial | Enumeration source for the 4 kindless providers undefined → risk of a vacuously-passing lock (R1-S5/F2). |
| FR-VCE-1 (`extract_view_prose()`) | §1 Group G FR-VCE-1 | Partial | `known_views` source is wrong/unspecified — graph yields model names not view names (R1-S3/F5). |
| FR-VCE-2 (close `Empty state:` dead-end) | §1 Group G FR-VCE-2; §0 D2 | Partial | Off-archetype `Empty state:` handling unspecified; back-compat loud-fail risk (R1-S4/F6). Verified dead-end at `extractors.py:241-245` and renderer fail at `renderers.py:1859`. |
| FR-VCE-3 (per-archetype validity, no new validator) | §1 Group G FR-VCE-3 | Full | Verified: renderer already loud-fails archetype-invalid combos (`renderers.py:1855-1885`). |
| FR-VCE-4 (display.yaml parity) | §1 Group G FR-VCE-4; §0 D3; §2 step 5 | Partial | Feasibility/authoring-gap gate missing; may need richer authoring than the doc carries (R1-S6/F7). |
| FR-KIN-1/2/3 (assembly-inputs consistency) | §1 Group B | Full | Pure docs; adequately scoped. |
| FR-FMT-1' (template View-copy keys) | §1 Group C FR-FMT-1'; §3 | Full | Authoring surface for FR-VCE-1; pairing stated. |
| FR-FMT-2 (reflective-loop conventions, pure doc) | §1 Group C FR-FMT-2; §0 D7 | Full | Verified zero machine consumption; pure doc as claimed. |
| FR-FMT-3 (Words/Structure rule) | §1 Group C FR-FMT-3 | Full | Doc addition. |
| FR-FMT-4 ($0-codegen AC checklist) | §1 Group C FR-FMT-3/4 | Partial | Listed but no per-item placement; minor. |
| FR-WCI-1 (wireframe view-copy coverage) | §1 Group D FR-WCI-1 | Partial | Should key by view ident not model to feed FR-WCI-2 correctly (R1-S8). |
| FR-WCI-2 (content-completeness rollup) | §1 Group D FR-WCI-2; §0 D9 | Partial | Rollup denominator depends on the view-name keyspace (R1-S8); schema-version bump noted. |
| FR-WCI-3 (capability-index entries) | §1 Group D FR-WCI-3 | Full | Two entries against the 12-field shape. |
| FR-DP-1 (name the prose-gated additive principle) | §1 Group F FR-DP-1; §0 D8 | Full | Principle doc; runtime-variant note included. |
| FR-DP-2 (DROPPED) | §1 Group F; §0 D8 | Full | Correctly dropped; folded into FR-DP-1. |
| FR-QW-1/2/3 (functional quick wins, group E) | (not covered) | Gap | §1 has no Group E implementation shape; §2 step ordering omits E except as "opportunistic." A thin §1 Group E note (even "deferred; renderers.py anchors as listed in reqs") would close the trace. |
