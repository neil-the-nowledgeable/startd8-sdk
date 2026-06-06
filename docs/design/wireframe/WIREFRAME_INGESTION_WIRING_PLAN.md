# Wireframe ↓ Plan Ingestion Wiring — Implementation Plan

**Version:** 1.2 (spike findings folded — extraction thesis empirically verified, P0/P1 grammar
rules pinned; supersedes 1.1 post-CRP merges; paired with
`WIREFRAME_INGESTION_WIRING_REQUIREMENTS.md` v0.4 + `KICKOFF_AUTHORING_CONTRACT.md` v0.2.
Evidence: [`spike-2026-06-05/SPIKE_FINDINGS.md`](spike-2026-06-05/SPIKE_FINDINGS.md) — 4/4
manifests round-trip clean from real strtd8 prose; pilot wireframe numbers hit at $0.)
**Date:** 2026-06-05
**Pilot:** the standing strtd8 request (`strtd8/docs/kickoff/VALIDATION_AND_MANIFEST_DERIVATION.md` §2)

## Guiding shape (from the planning pass)

Everything lands on **existing seams** — no refactors: emission is a sub-step of the EMIT
phase using the established `atomic_write_json` pattern; extraction reuses the SDK's existing
markdown section/list parsers plus one small stdlib table parser; the wireframe consumes the
emitted manifests through the same generator parsers it already imports; and the cap-dev-pipe
invocation point **already exists post-ingestion / pre-prime** (`run-prime-contractor.sh:212`).
The one genuinely new emitter (a Prisma writer) is **deferred** — the pilot diffs against the
existing contract instead.

```
P0  Extraction module (grammars → values, stdlib-only)            FR-WPI-2/3
P1  Per-manifest extractors + round-trip validation               FR-WPI-1/2/4
P2  EMIT wiring (manifests/ + extraction report)                  FR-WPI-1/3
P3  Wireframe --from-run + fingerprint linkage                    FR-WPI-6/7
P4  Per-phase delivery inventory                                  FR-WPI-9
P5  Promotion (documented manual + inventory flip)                FR-WPI-5
P6  strtd8 pilot to acceptance                                    §4 snapshot
P7  [deferred] Prisma emitter for greenfield contract drafting    FR-WPI-8 (greenfield half)
```

## P0 — Extraction module: `src/startd8/manifest_extraction/`

- `sections.py` — reuse `document_chunking._parse_sections()` (heading tree,
  `document_chunking.py:377`) + `implementation_engine/parsers.py` `parse_list_section`/
  `parse_section_content` (:36/:58). Add `parse_md_table()` — small line-based stdlib parser
  for `| a | b |` tables (the only missing primitive; no new deps). **Spike-pinned rules:**
  tables segment as maximal consecutive-`|` runs (F1 — adjacent Pages+Nav tables; encode the
  21-phantom-pages regression as a P0 test); route/slug derivation applies NFKD normalization
  (F2 — `Résumé` → `/resume`); cell annotations stripped (`jobs.md *(not written yet)*` →
  `jobs.md`). Spike's `spike.py` (this dir's `spike-2026-06-05/`) is the grammar test-case
  source — supersede, don't reuse.
- `report.py` — `ExtractionReport` model: per manifest, per value →
  `extracted(source: §/row/sentence) | not_extracted(reason) | defaulted(source)`; JSON +
  derived `.md` review form (FR-J2).
- Grammar version constant pinned to the authoring contract **v0.2** (+ corpus-snapshot field,
  advisory).
- **Grammar-contract gate (CRP R2-S4):** P0 coding MUST NOT begin until the contract's grammar
  decisions (R1-G1–G4) show Accepted in its Appendix A — **satisfied 2026-06-05** (contract
  v0.2); the gate stays as a regression guard for future grammar growth.
- **FR-WPI-11 homes (CRP R1-S4):** corpus-snapshot field lands here (P0); synonym consultation
  + determinism-sample emission are **explicitly deferred until the corpus ships** (one line in
  the extractor marking the seam; no dormant code).

## P1 — Per-manifest extractors (each: extract → emit YAML → round-trip through the generator's parser)

Emission via `yaml.safe_dump(sort_keys=False, allow_unicode=True)` (the codebase standard);
round-trip targets verified at:

| Manifest | Extractor source (REQUIREMENTS section) | Round-trip parser | Notes |
|---|---|---|---|
| `app.yaml` | Scaffold & runtime table | `scaffold_codegen/manifest.py:32` `parse_app_manifest` (keys: app/persistence/logging/migrations/container) | env-keys agreement check vs `build-preferences.yaml`; absent section ⇒ defaults (skip emission, statuses `defaults`). **Sweep 2:** §2.7's `port`/`env keys`/`sqlite mode` have no `AppManifest` home → `not_extracted(generator-gap)`, never unknown keys (the strtd8 `database`/`env` drift class, regression-tested) |
| `pages.yaml` | Pages + Nav tables | `pages_generator.py:67` `parse_pages` (slug/title/content + nav label/href) | slugs derived kebab(title); Home → `/` |
| `views.yaml` | Views blocks | `view_codegen/manifest.py:100` `parse_views` — **`route` is a required key**, so the kind-aware derivation runs HERE and writes explicit routes (contract §2.3; `Route:` line overrides) | sub-schemas: aggregates/relations/polymorphic/panels/gap per :22–31. **Spike-pinned (F3/F5/F6):** Nav-table targets take route precedence over derivation; dashboards' `counts of X per <root>` → schema-resolved aggregates (verified: `tailored_matches_count/of: TailoredMatch/fk: jobDescriptionId`); detail-compose/workspace `Shows:` is prose → v1 emits kind/root/route **shells** (parser-clean), `shows`/`Also shows:`/`Empty state:`/`Formats:` flagged `not_extracted` |
| `ai_passes.yaml` | AI-assists table | `ai_layer.py:108` `parse_ai_passes` | prompt path = `prompts/<name>.md` |
| `human_inputs.yaml` | Owned-fields line + `ONLY HUMANS ENTER THIS` field notes | `ai_layer.py:144` `parse_human_inputs` | both sources merge to one policy |
| `completeness.yaml` | Completeness sentences | `derived.py:250` tolerant loader — **SDK accepts only `exclude` + `entities.{min_rows,weight}`** | emit the SDK schema; nudges/predicate/confirmed/href flagged `not_extracted(generator-gap)` **per entry** (CRP R2-G5). **Strict emission-side validator (CRP R1-S2):** assert the emitted dict contains ONLY the accepted shapes before write — the tolerant loader validates nothing, so FR-WPI-4's round-trip is vacuous here without it. Runs AFTER the relationship pass ("connection records" → derived join-model names, CRP R2-F5) |
| `schema.prisma` | Entities blocks | `prisma_parser.py` (lenient + recoverability) | **pilot = DIFF mode only** (entity tables vs live contract → drift report); greenfield drafting needs the P7 emitter |

## P2 — EMIT wiring (plan ingestion)

- New `PhaseEmitter._emit_manifests()` sub-step inside `emit()` orchestration
  (`plan_ingestion_emitter.py:115–355`), writing `output_dir/manifests/*` +
  `manifest-extraction-report.{json,md}` via `atomic_write_json`/text; entries added to the
  `artifacts_out` dict (`:845–931`).
- **Thread the requirements docs**: plan raw text is already available
  (`ParsedPlan.raw_text`, `workflow.py:1560`), but requirements docs are loaded only in
  `_execute()` (`workflow.py:4051`) — extend `emit()`'s signature to receive them (the one
  signature change in the whole plan).
- No phase-enum change, no checkpoint interaction (phases are sequential in-memory): emission
  is deterministic, no flag needed (mirrors-inverts the `enable_llm_*` precedent — there is no
  LLM path to gate).

## P3 — Wireframe `--from-run`

- `cli_wireframe.py`: new `--from-run <run-dir>` option; resolves each manifest key to
  `<run-dir>/manifests/<file>` and passes them as the existing flag-style overrides
  (CLI-level mapping beat the v0.1 "fourth resolution tier" idea).
- **Sweep-2 correction — one `inputs.py` change IS needed:** flag overrides pass through
  `_confine()` (FR-W6/R3-F4), which exits 2 for paths outside `project_root` — canonical
  cap-dev-pipe run dirs live at `$PROCESS_HOME/pipeline-output/` *outside* the consumer project
  (`run-cap-delivery.sh:56,150`); only embedded runs are inside. `load_assembly_inputs` gains an
  optional `extra_root` (the explicit `--from-run` dir) accepted by confinement; flag paths and
  `--inputs` files keep single-root semantics. `--from-run` composes with `--project` (still
  the app root for content-inputs checks). Test both layouts (embedded + canonical).
- **Provenance-file resolver (CRP R2-S1):** when `--from-run` receives a `*.json` path, read
  `output_dir` from the provenance JSON to locate `manifests/` — the standard cap-dev-pipe
  invocation passes a provenance file, not a dir; test both forms produce identical wireframes.
- **Confinement mechanics (CRP R1-S3/R2-S5; spec in FR-WPI-6):** `extra_root` is `.resolve()`d
  before comparison; allowance origin-keyed to `--from-run`-synthesized entries; advisory
  warnings for foreign-run (provenance ≠ `--project`) and world-writable/unowned run dirs.
- Plan JSON additions (additive, `schema_version` stays 1): `run_linkage{source_doc_checksums,
  extraction_report_sha256, seed_checksum, run_dir}` — joins the existing `inputs_fingerprint` +
  `claimed_paths` (`render.py:54–85`). **Per FR-WPI-7 hash semantics (CRP R2):** manifest hashes
  = parsed canonical model (not YAML bytes); `run_dir` = resolved canonical path;
  `source_doc_checksums` + `seed_checksum` are provenance-only (excluded from the re-walk
  trigger — the seed churns on LLM non-determinism); the FR-WPI-10 gate binds to the stable
  `run_linkage` slice, never the whole plan artifact (rendering metadata churns per invocation).

## P4 — Per-phase delivery inventory

- Static kind→iteration map (scaffold/entities/CRUD → 1; pages/views/completeness/export → 2;
  AI passes/prompts/content → 3) — manifests carry no phase tags today and don't need them.
- `phase` field on `WireframeItem` + a grouped inventory rendering (`render.py:122–179` seam);
  surfaced in the default tree and `--json`; markdown form reuses the pipeline shim's
  `wireframe-summary.md` writer (resolves OQ-5: both terminal and shareable md exist).

## P5 — Promotion (lightest mechanism that records the act)

Documented manual step: copy `manifests/*` → project conventional paths, flip the inventory
Status rows (`extracted` → `authored`) — per the Q2/Q5 operator-coordinated spirit. The
`startd8 assist` drift check then owns ongoing divergence. (A `promote-manifests` subcommand is
a follow-up, not v1.) Re-extraction diff-not-overwrite applies only to *promoted* manifests;
the strtd8 INVALID trio is superseded, not diffed.

## P6 — strtd8 pilot (their §2 acceptance, verbatim)

`startd8 wireframe --only-issues` loop → `scaffold|backend|views: ready`; 16 entities /
80 CRUD routes; nav includes Target Roles after Profile; `COST_BUDGET_USD` default 10.00;
`Metric.value` omitted from every generated form; extraction report traces every value;
contract DIFF clean against `fe1eab3`+.

**P6 deliverable (CRP R1-S4):** the cap-dev-pipe ordering documentation — ingestion → wireframe
→ *operator confirms walkthrough* → prime contractor — written into the pipeline docs as part
of the pilot close-out (FR-WPI-10's documentation half).

## P7 — Deferred: Prisma emitter

No Prisma writer exists anywhere in the codebase (parse-only today) — required only for
greenfield contract drafting (FR-WPI-8's "draft fresh" path). Reference pattern:
`scaffold_codegen/renderers.py` text rendering. Own mini-loop when scheduled.

## Test plan

- Unit per extractor: golden REQUIREMENTS fixture → expected YAML, byte-stable; malformed
  section → `not_extracted` + reason (never a guess).
- **Ambiguity-fixture corpus (CRP R1-S1 — harvested from the worked instance):** annotated
  entity headings, `### View: … *(P2 preview)*` headings, `links to many` + symmetric-dedup
  set (6 sentences → exactly 3 join models), "links X to nothing" → flagged, plural refs,
  the AiCall slash-row → flagged, §2.7 rich cells (database URL / logging / env keys), nav
  targets at non-manifest routes → verbatim + advisory, completeness nudge suffix → two report
  rows, `Kind: board` without `Group by:` → flagged, kebab collisions → both flagged,
  `Résumé` → `resume`, `Metadata` entity → reserved-name flag. Each with one asserted outcome;
  CI fails on any silent flip.
- Round-trip: every emitted manifest parses through its generator parser (the FR-WPI-4
  invariant as a test) + the strict completeness emission validator (R1-S2).
- Cross-check: wireframe plan from `--from-run` ≡ plan from the same manifests at conventional
  paths (FR-W14 extension) ≡ plan via the provenance-file form (R2-S1).
- **Confinement tests (R1-S3/R2-S3/R2-S5):** symlinked manifest escaping both roots → exit 2;
  `--inputs` file under the run dir but outside project root → exit 2; cross-project
  `--from-run <strtd8-run> --project <other-root>` → advisory warning, manifests read, exit 0;
  world-writable run dir → advisory.
- **Fingerprint stability (R1-F2/R2-S2/R2-S6/R2-F4):** edit never-extracted prose → gate
  closed; LLM-seed churn on identical inputs → gate closed; YAML key-order reformat → hashes
  unchanged; two symlink spellings of one run dir → identical `run_linkage`; edit a pages-table
  row → gate re-opens.
- Pilot fixture: a trimmed strtd8 REQUIREMENTS_v0.5 excerpt as the canonical end-to-end test.

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
| R1-S1 | Ambiguity-fixture corpus from the worked instance | R1 (opus); endorsed R2 | Test plan: 13-case corpus with asserted outcomes | 2026-06-05 |
| R1-S2 | Strict emission-side completeness validator (tolerant loader = vacuous round-trip) | R1 (opus); endorsed R2 | P1 completeness row + Test plan round-trip bullet | 2026-06-05 |
| R1-S3 | `extra_root` mechanics + confinement tests | R1 (opus); endorsed R2 | P3 confinement bullet; Test plan confinement set; spec in FR-WPI-6 | 2026-06-05 |
| R1-S4 | Plan homes for FR-WPI-11 behaviors + FR-WPI-10 ordering doc | R1 (opus) | P0 deferred-seam note; P6 deliverable | 2026-06-05 |
| R2-S1 | Provenance-file resolver for `--from-run <*.json>` | R2 (sonnet) | P3 resolver bullet + cross-check test (the standard cap-dev-pipe invocation form) | 2026-06-05 |
| R2-S2 | `seed_checksum` provenance-only (LLM churn must not re-open the gate) | R2 (sonnet) | P3 `run_linkage` notes; FR-WPI-7/10 clauses | 2026-06-05 |
| R2-S3 | Cross-project `--from-run` advisory test | R2 (sonnet) | Test plan confinement set | 2026-06-05 |
| R2-S4 | Grammar-contract gate on P0 | R2 (sonnet) | P0 gate note — satisfied 2026-06-05 (contract v0.2); retained as regression guard | 2026-06-05 |
| R2-S5 | World-writable/unowned run-dir advisory | R2 (sonnet, adversarial) | P3 confinement bullet; FR-WPI-6(iii); test | 2026-06-05 |
| R2-S6 | Gate binds to the stable `run_linkage` slice, never the whole plan artifact | R2 (sonnet, adversarial) | P3 notes; FR-WPI-10 trigger-scope clause; fingerprint-stability tests | 2026-06-05 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-05

- **Reviewer**: Claude Opus 4.8 (claude-opus-4-8-1m)
- **Date**: 2026-06-05 23:23:38 UTC
- **Scope**: Dual-doc review (plan side) per `crp-focus-wiring-grammars.md`; grammars tested against the strtd8 worked instance; parsers spot-verified read-only. Focus-ask answers live in the requirements file's R1 block; contract grammar suggestions (R1-G\*) in `KICKOFF_AUTHORING_CONTRACT.md`.

##### Executive summary

- The test plan's single "trimmed strtd8 excerpt" fixture will not lock the grammar edges the worked instance already exhibits (plural refs, annotated headings, `links to many`, slash-rows, rich §2.7 cells) — an ambiguity-fixture corpus is the cheapest way to make P0/P1 deterministic in practice, not just in intent.
- FR-WPI-4's "schema-valid by construction" is vacuous for `completeness.yaml`: the round-trip target is a tolerant loader that accepts any mapping.
- P3's `extra_root` needs resolved-path + origin-keyed semantics stated, or the confinement guarantee is correct only by luck.
- FR-WPI-11's two active behaviors have no P-step home; FR-WPI-10's operator-confirm ordering documentation likewise.

##### Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Validation | high | Add an ambiguity-fixture corpus to the test plan, harvested from the worked instance: annotated entity headings (`### TargetRole *(added …)*`), `links to many` + "links X to nothing" sentences, plural entity references ("at least 3 ProofPoints"), the two-fields-one-row AiCall cell (`promptTokens / responseTokens`), the §2.7 `env keys`/`database`/`logging` rich cells, nav targets pointing at non-page routes, and the `jobs.md *(not written yet)*` annotated cell — each with an asserted outcome (extracted value or `not_extracted(reason)`) | The "trimmed strtd8 REQUIREMENTS_v0.5 excerpt" fixture exercises the happy path; every listed shape exists today in the reference consumer's conforming doc and is exactly where two implementations diverge — golden-asserting them pins the grammar decisions R1-G1–G5 propose | Test plan section, new bullet after "Pilot fixture" | Each fixture has one asserted outcome; CI fails when an extractor change flips any outcome silently |
| R1-S2 | Validation | high | P1 completeness row: add a strict emission-side validator — assert the emitted dict contains only `exclude` + `entities.{min_rows,weight}` shapes (correct types, known keys) before write — because the declared round-trip target `derived.py:250` is a tolerant loader (returns any mapping as-is, `None` on bad) and validates nothing | FR-WPI-4 claims emitted manifests "parse clean through the generators' own parsers", but for this manifest the parser cannot fail — the exact drift class FR-WPI-4 exists to prevent would pass this round-trip undetected | P1 table, `completeness.yaml` row Notes | Unit test: feed the validator a nudge/predicate-bearing dict → rejected at emission; the tolerant loader alone would have accepted it |
| R1-S3 | Security | medium | P3: state the confinement mechanics — `extra_root` is `.resolve()`d before comparison; the allowance is origin-keyed to the entries the `--from-run` mapping synthesizes (not a global second root); add tests: symlinked manifest inside the run dir escaping both roots → exit 2; `--inputs` file under the run dir but outside project root → exit 2; plus an advisory foreign-run warning when run provenance ≠ `--project` | The sweep-2 correction states *that* `inputs.py` gains the allowance but not *how* scoped; `_confine` (`inputs.py:78–81`) is prefix-after-resolve, so the guarantee holds only if the new root is resolved too and unreachable from other origins | P3, after the `load_assembly_inputs` sentence; Test plan | The three named tests exist and pass; both layouts (embedded + canonical) covered as already planned |
| R1-S4 | Ops | medium | Give FR-WPI-11(a)/(b) and FR-WPI-10's operator-confirm ordering documentation explicit plan homes: corpus synonym consultation + determinism-sample emission as a P0/P2 sub-bullet (or an explicit "deferred until corpus ships" line), and the cap-dev-pipe ordering doc (ingestion → wireframe → operator confirms → prime) as a P6 deliverable | P0 carries only the corpus-snapshot field; the FR's two active behaviors and the FR-WPI-10 documentation task appear in no P-step — unplanned scope either silently drops or silently grows | P0 (corpus sub-bullet) and P6 (ordering doc) | Coverage matrix rows for FR-WPI-10/11 move from Partial/Gap to Covered |

##### Endorsements & Disagreements

None — Appendix C was empty before this round (first review).

## Requirements Coverage Matrix — R1

| Requirement Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-WPI-1 — Manifest emission artifacts | P0, P2 | Covered | — |
| FR-WPI-2 — Deterministic, flag-never-guess | P0, P1, Test plan (malformed → `not_extracted`) | Covered | — |
| FR-WPI-3 — Extraction report | P0 (`report.py`), P2 | Partial | Per-value identity, ordering, and locator form unspecified (R1-F1) |
| FR-WPI-4 — Schema-valid by construction | P1 (round-trip per row) | Partial | Completeness round-trip target is a tolerant loader — validates nothing (R1-S2) |
| FR-WPI-5 — Promotion ratchet | P5 | Covered | — |
| FR-WPI-6 — `--from-run` mode | P3 | Partial | `extra_root` resolution order, origin-keying, symlink tests unstated (R1-S3/R1-F3) |
| FR-WPI-7 — Fingerprint linkage | P3 (`run_linkage` additions) | Covered | — |
| FR-WPI-8 — FR-F3 amendment (DIFF/DRAFT) | P1 (`schema.prisma` DIFF row), P7 (DRAFT, deferred) | Covered | DRAFT half deferred by design (settled — P7) |
| FR-WPI-9 — Per-phase delivery inventory | P4 | Covered | — |
| FR-WPI-10 — Acceptance gate | P3 (linkage), P6 (pilot); invocation point pre-exists | Partial | Operator-confirm ordering documentation has no P-step home (R1-S4); re-walk trigger scope over-broad (R1-F2) |
| FR-WPI-11 — Controlled-corpus alignment | P0 (corpus-snapshot field only) | Gap | Synonym consultation (a) and determinism-sample emission (b) appear in no P-step (R1-S4) |
| §3 Non-Requirements | Guiding shape, P2 (no LLM path), P5 (no auto-promotion) | Covered | — |
| §4 Acceptance Snapshot (strtd8 pilot) | P6 | Covered | — |

#### Review Round R2 — claude-sonnet-4-6 — 2026-06-06

- **Reviewer**: claude-sonnet-4-6
- **Date**: 2026-06-06 00:00:00 UTC
- **Scope**: Dual-doc review (plan side) R2; second-order effects of R1 findings; adversarial grammar pass against the worked instance; `extra_root` trust argument attack; fingerprint ceremony loopholes.

##### Executive summary

- P3 describes `--from-run <run-dir|provenance>` but the plan only implements the run-dir resolver; the provenance-file path to `manifests/` is a distinct lookup that has no implementation step.
- FR-WPI-7's `seed_checksum` in `run_linkage` is LLM-path output — it churns independently of kickoff-doc edits, creating phantom fingerprint differences unrelated to extractable content; this is a second-order effect of R1-F2's trigger-scoping concern.
- P3's test plan covers embedded + canonical layouts but not the cross-project case: `--from-run <run-dir> --project <different-app-root>` — the pilot is same-project, so this gap never fires in P6.
- No plan step names the extractor's dependency on R1-G* grammar decisions — P0 can be code-complete without resolving relationship-verb ambiguity, and the pilot (P6) will catch the failure only at the strtd8 fixture, not earlier.

##### Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Interfaces | high | P3: add the provenance-file resolver as an explicit sub-step — when `--from-run` receives a `*.json` path (provenance file), the resolver reads `output_dir` from the provenance JSON to locate the `manifests/` dir; add this to the test plan (provenance-file path → same manifests as run-dir path). FR-WPI-6 says `<run-dir\|provenance>` but P3 only describes the run-dir case. | `render.py` already reads provenance (`render.py:54–85`); the resolver is one lookup but if unimplemented `--from-run <provenance.json>` silently fails or errors at runtime — the cap-dev-pipe standard invocation passes a provenance file, not a dir. | P3, new bullet after "resolves each manifest key"; Test plan | `--from-run pipeline-output/run/run-provenance.json` → same wireframe as `--from-run pipeline-output/run/` |
| R2-S2 | Data | medium | P3 `run_linkage`: demote `seed_checksum` from the fingerprint's re-walk trigger to a provenance-only field (same treatment R1-F2 proposes for `source_doc_checksums`). The seed (`prime-context-seed.json`) is LLM-path output that changes between runs even when the kickoff docs are identical — tying the acceptance re-walk to it re-opens the gate on an LLM non-determinism artifact. | "Plan JSON additions: `run_linkage{source_doc_checksums, extraction_report_sha256, seed_checksum}`" — all three feed the fingerprint today; R1-F2 is already scoping out `source_doc_checksums`; `seed_checksum` has the same problem amplified because LLM calls are inherently non-deterministic. | P3, `run_linkage` sentence; cross-ref FR-WPI-7 and R1-F2 | Two identical-input runs with different LLM seed output → fingerprint unchanged; acceptance gate stays closed |
| R2-S3 | Validation | medium | Test plan: add the cross-project `--from-run` case — `--from-run <rundir> --project <different-project-root>` should warn (not exit) that the run's provenance doesn't match the project root (the R1-S3 foreign-run advisory), and manifests are still read. The P6 pilot is always same-project so this never exercises the advisory path. | The advisory warning R1-S3 proposes is only observable when `--project` and `--from-run` point at different apps; a missing test means the advisory could be silently omitted during implementation with no CI signal. | Test plan, new bullet after "Both layouts (embedded + canonical)" | Test: `--from-run <strtd8-run> --project <other-app-root>` → warning emitted, manifests read, exit 0 |
| R2-S4 | Risks | medium | P0/P1: add an explicit note that the extraction module's behavior for relationship verbs, view key mapping, and name-derivation rules is **blocked on the authoring-contract grammar decisions** (R1-G1–G4) — if those are unresolved at implementation time, P0 implementers will make the grammar choices implicitly, producing exactly the divergence the contract is meant to prevent. Mark P0 with a "grammar-contract gate: KICKOFF_AUTHORING_CONTRACT.md §2 decisions (R1-G1–G4) must be resolved before P0 coding". | The plan has no sequencing constraint between resolving grammar ambiguity and writing the extractor; two developers starting P0 in parallel without the contract decisions would build divergent implementations for `links to many`, view-key mapping, and heading annotation stripping. | P0 guiding text, new sentence; or a gate note in the P0 bullet | Reviewer confirms R1-G1–G4 are marked Accepted in `KICKOFF_AUTHORING_CONTRACT.md` Appendix A before P0 coding begins |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S5 | Security | medium | Attack the `extra_root` confinement: a `--from-run` pointing at a directory the *operator doesn't own* (e.g. a world-writable `/tmp/shared-runs/`) still passes confinement if `extra_root` is resolved correctly — the trust argument is "explicit operator flag" but the flag value is an arbitrary path. Add an advisory (not a gate) when `extra_root` is world-writable or not owned by the invoking user. The read-only blast radius argument (R1 Ask 3) holds, but a world-writable run dir is a trivially exploitable manifest injection point. | A hostile/poisoned `--from-run` dir where an attacker pre-seeded `views.yaml` with a crafted payload produces a plausible walkthrough with adversarial route strings; the wireframe writes its plan artifact from it — the injection reaches the acceptance artifact. The existing confinement (resolving the path) doesn't check ownership. | P3, confinement notes; FR-WPI-6 amendment parenthetical | Test: `--from-run /tmp/world-writable-dir` → advisory warning emitted |
| R2-S6 | Validation | low | Fingerprint/re-walk ceremony loophole: an implementer could satisfy FR-WPI-10's "hash-bound per FR-J3" by binding acceptance to the whole wireframe-plan JSON checksum — but the plan JSON contains rendering metadata (timestamps, run durations) that changes every invocation. Spec that the re-walk fingerprint binds to the `run_linkage` sub-object only (the stable provenance slice), not the whole plan artifact. | "Acceptance binds to the wireframe-plan fingerprint" is ambiguous; if implemented as a whole-file hash, every wireframe invocation re-opens the gate (the rendering timestamp changes). | FR-WPI-10, the hash-bound clause; P3 `run_linkage` sentence | Test: re-invoke wireframe on identical inputs → fingerprint unchanged; add a known non-stable field to the plan artifact → fingerprint still unchanged |

##### Endorsements & Disagreements

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R1-S1: Ambiguity-fixture corpus is essential before P0 coding — endorsing; especially the `links to many` and nav-target-pointing-at-non-page-route cases which the adversarial pass confirms are non-obvious.
- R1-S2: Strict emission-side completeness validator — endorsing; the tolerant loader is the exact gap the extractor-implementer would miss.
- R1-S3: `extra_root` origin-keying and resolve semantics — endorsing; confirmed by reading `_confine` (`inputs.py:78–81`) that the new root must itself be resolved pre-comparison.
- R1-F2: Re-walk trigger scoped to extraction-relevant content — endorsing; R2-S2 extends this to cover `seed_checksum` as a second instance of the same problem.
- R1-G1: Relationship grammar disambiguation — endorsing; the worked instance uses `links to many` on three entities (`ProofPoint`, `Capability`, `Outcome`), producing symmetric restatements that must dedup to the exact join models listed in the §4 acceptance snapshot ("Connection records: ProofPoint↔Capability, ProofPoint↔Outcome, Capability↔Outcome").

## Requirements Coverage Matrix — R2

| Requirement Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-WPI-1 — Manifest emission artifacts | P0, P2 | Covered | — |
| FR-WPI-2 — Deterministic, flag-never-guess | P0, P1, Test plan (malformed → `not_extracted`) | Covered | — |
| FR-WPI-3 — Extraction report | P0 (`report.py`), P2 | Partial | Per-value identity, ordering (R1-F1 untriaged) |
| FR-WPI-4 — Schema-valid by construction | P1 (round-trip per row) | Partial | Completeness vacuous round-trip (R1-S2 untriaged); grammar-contract gate on P0 (R2-S4) |
| FR-WPI-5 — Promotion ratchet | P5 | Covered | — |
| FR-WPI-6 — `--from-run` mode | P3 | Partial | Provenance-file resolver missing (R2-S1); `extra_root` scoping (R1-S3 untriaged) |
| FR-WPI-7 — Fingerprint linkage | P3 (`run_linkage` additions) | Partial | `seed_checksum` churns on LLM non-determinism (R2-S2) |
| FR-WPI-8 — FR-F3 amendment (DIFF/DRAFT) | P1 (`schema.prisma` DIFF row), P7 (DRAFT, deferred) | Covered | DRAFT half deferred by design (settled — P7) |
| FR-WPI-9 — Per-phase delivery inventory | P4 | Covered | — |
| FR-WPI-10 — Acceptance gate | P3 (linkage), P6 (pilot); invocation point pre-exists | Partial | Ordering doc (R1-S4 untriaged); re-walk trigger over-broad (R1-F2 untriaged); whole-plan-hash loophole (R2-S6) |
| FR-WPI-11 — Controlled-corpus alignment | P0 (corpus-snapshot field only) | Gap | Synonym consultation + determinism-sample emission unplanned (R1-S4 untriaged) |
| §3 Non-Requirements | Guiding shape, P2 (no LLM path), P5 (no auto-promotion) | Covered | — |
| §4 Acceptance Snapshot (strtd8 pilot) | P6 | Covered | — |
