# Wireframe ↓ Plan Ingestion Wiring — Requirements

**Version:** 0.4 (spike findings folded in — extraction thesis EMPIRICALLY VERIFIED on real
strtd8 prose, F1–F6 grammar rules into FR-WPI-2/4; supersedes 0.3 post-CRP — R1 opus + R2
sonnet triaged: 30 doc-set suggestions, ACCEPT 30 / REJECT 0; paired plan
[`WIREFRAME_INGESTION_WIRING_PLAN.md`](WIREFRAME_INGESTION_WIRING_PLAN.md) v1.2, authoring
contract v0.2)
**Date:** 2026-06-05
**Status:** Draft
**Scope:** Wire the wireframe explicitly **downstream of plan ingestion**: ingestion gains
deterministic **manifest emission**; the wireframe gains a run-consumption mode, end-to-end
fingerprint linkage, and per-phase delivery-inventory rendering — making the wireframe the
**business acceptance gate** between kickoff and the prime contractor.
**Related:**
- [`WIREFRAME_REQUIREMENTS.md`](WIREFRAME_REQUIREMENTS.md) v0.4 (FR-W1–W16 — extended, not
  amended; anti-divergence FR-W14, advisory FR-W9, and the §1.0 consumer-agnostic positioning
  are load-bearing here — strtd8 stays the *reference consumer*, never the target)
- [`../kickoff/KICKOFF_AUTHORING_CONTRACT.md`](../kickoff/KICKOFF_AUTHORING_CONTRACT.md) — the
  happy-path language this pipeline extracts from
- `../plan-ingestion/DETERMINISTIC_INGESTION_REQUIREMENTS.md` — the promote-deterministic-paths
  precedent this extends
- [`../kickoff/KICKOFF_ASSEMBLY_INPUTS.md`](../kickoff/KICKOFF_ASSEMBLY_INPUTS.md) FR-F3 —
  amended by FR-WPI-8
- [`../HITM_ROLE_MODEL_REQUIREMENTS.md`](../HITM_ROLE_MODEL_REQUIREMENTS.md) — Customer/PO gate
  (§3.0), Architect gate (§3.3), FR-J3 hash-bound gate rule

---

## 0. Planning Insights (Self-Reflective Update)

> The planning pass (2026-06-05, three parallel code sweeps: ingestion emitter seams, wireframe
> extension seams, generator parser/emitter surfaces) verified every §6 checklist item and
> corrected the draft in 8 places — the loop working as intended. Net effect: **scope shrank**
> (everything lands on existing seams; one emitter deferred) and one new vocabulary-drift
> instance surfaced.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| The cap-dev-pipe gate needs a NEW post-ingestion/pre-contractor placement | The `STARTD8_WIREFRAME=1` hook **already runs post-ingestion / pre-prime** (`run-prime-contractor.sh:212` — after stage-5 plan ingestion, before workflow launch) | FR-WPI-10's invocation point exists today; only the operator-confirm ordering note remains |
| Manifest emission might be a new ingestion phase (OQ-1) | Phases are **sequential in-memory, no inter-phase checkpoints**; the artifact seam is the `artifacts_out` dict + `atomic_write_json` (`plan_ingestion_emitter.py:845–931`) | **OQ-1 resolved:** emission is a sub-step of EMIT orchestration — no phase-enum change, no resume interaction |
| Raw kickoff docs available at emission time | Plan raw text yes (`ParsedPlan.raw_text`, `workflow.py:1560`); **requirements docs are not threaded to EMIT** (loaded only in `_execute()`, `workflow.py:4051`) | One signature extension to `PhaseEmitter.emit()` — the only signature change in the plan |
| Extraction grammars may need a new parser module | Section/list parsers **exist** (`document_chunking._parse_sections:377`, `implementation_engine/parsers.py:36/58`); only a small stdlib markdown-**table** parser is missing | No new deps confirmed; P0 is one small primitive + reuse |
| Kind-aware view-route derivation might touch `view_codegen` | `parse_views` **requires** an explicit `route` key (`view_codegen/manifest.py:117`) | Derivation runs in the **extraction phase** and writes explicit routes — zero generator change; the contract §2.3 answer stands |
| The completeness grammar maps onto the SDK manifest | **Fourth vocabulary-drift instance:** the SDK loader accepts only `exclude` + `entities.{min_rows, weight}` (`derived.py:250`, tolerant); strtd8's richer shape (`predicate/confirmed/nudge/href/formula/gate/order`) is generator-unsupported — its own file header predicted the reconciliation | Extraction emits the SDK schema; the rich fields are flagged `not_extracted(generator-gap)` in the report — a visible backlog item, never silently dropped |
| Contract drafting (Prisma emission) is in pilot scope | **No Prisma writer exists anywhere** in the codebase (parse-only) | FR-WPI-8's greenfield-drafting half **deferred to P7**; the strtd8 pilot needs only DIFF mode (their contract exists), per their OQ-4 answer |
| `inputs.py` needs a fourth resolution tier for `--from-run` | CLI-level mapping (run-dir manifests passed as existing flag-style overrides) is sufficient | Smaller change; `inputs.py` untouched — **corrected by sweep 2 (below): one confinement allowance IS needed** |

> **Second planning sweep (same day, independent code verification — emitter, cap-dev-pipe
> scripts, authoring contract §2.7, wireframe inputs/confinement):** converged with the table
> above on OQ-1/phase-mapping/parser-reuse, and added two discoveries:

| v0.2 Assumption | Sweep-2 Discovery | Impact |
|-----------------|-------------------|--------|
| Flag-style overrides suffice for `--from-run` (row above) | **Path confinement (FR-W6/R3-F4) exits 2 for any path outside `project_root`** — and canonical (non-embedded) cap-dev-pipe puts run dirs at `$PROCESS_HOME/pipeline-output/`, *outside* the consumer project (`run-cap-delivery.sh:56,150`); only embedded runs (`<project>/.cap-dev-pipe/pipeline-output/`, the strtd8 layout) are inside | FR-WPI-6 amended: the explicit `--from-run` dir is a **second permitted root** (same trust basis as any explicit flag); `inputs.py` gains that one allowance. Flag paths and `--inputs` files keep single-root semantics |
| §2.7 maps fully onto `app.yaml` | **Fifth vocabulary-drift instance:** §2.7's settings vocabulary includes `port`, `env keys`, `sqlite mode` — none representable in `AppManifest` (`scaffold_codegen/manifest.py:19-30`: name/package/python_version/db_path/log_file/migrations/dockerfile only). strtd8's invalid `app.yaml` (unknown keys `database`/`env`) is this exact drift, hand-authored | Same treatment as the completeness gap: emit the SDK schema; unrepresentable settings flagged `not_extracted(generator-gap)` — scaffold-codegen backlog, never invented keys |

**Resolved open questions:** OQ-1 (EMIT sub-step) · OQ-2 (partial conformance: **yes** — emit
what conforms; the wireframe's status machinery renders the rest honestly) · OQ-3 (promotion =
documented manual copy + inventory status flip, Q2/Q5 spirit; CLI subcommand is follow-up) ·
OQ-4 (strtd8 = DIFF mode, confirmed feasible) · OQ-5 (both: terminal tree + the pipeline shim's
existing `wireframe-summary.md` writer reused for a shareable form).

> **Spike verification (2026-06-05, third evidence pass — empirical; full report:
> [`spike-2026-06-05/SPIKE_FINDINGS.md`](spike-2026-06-05/SPIKE_FINDINGS.md)):** ~300 lines of
> throwaway stdlib parsing against the REAL strtd8 `REQUIREMENTS_v0.5-draft.md` — **the
> extraction thesis holds on first contact.** 4/4 attempted manifests (pages/app/views/
> completeness) round-trip clean through the generators' parsers; the wireframe on the
> extracted set + real contract hits the pilot acceptance exactly (`ready`×3, **16 entities /
> 80 CRUD routes**, `Target Roles` in nav, `Metric.value` owned-omitted), correctly deriving
> past the exact drift keys that invalidated the hand-authored trio. Six findings (F1–F6)
> folded into FR-WPI-2/4 below: adjacent-table segmentation, NFKD route normalization,
> `Shows:`-is-prose for detail-compose/workspace (→ v1 shells), join-model category expansion
> (independently confirms the CRP R2 ordering constraint), ungrammared view lines, nav-table
> route authority.

---

## 1. Problem Statement & the Vision This Serves

**Operator-stated vision (2026-06-05):**

```
customer prose ("what I want built")
  → LLM+human co-work → kickoff docs in the HAPPY-PATH FORMAT       (the one LLM spend)
  → plan ingestion: DETERMINISTIC extraction → assembly manifests (+ seed)
  → wireframe → business-user lo-fi walkthrough                    (the ACCEPTANCE GATE)
  → prime contractor iterations: ① framework+persistence
                                 ② display+business logic
                                 ③ integration+content population
```

**The rule:** the format carries the truth; LLMs only carry you to the format. Values a
formatted document determines (routes from a pages table, fields from an entity table) are
**extracted, never generated** — the past anti-pattern (LLM-generating routes) is structurally
prevented.

### Gap table

| Component | Current state | Gap |
|-----------|---------------|-----|
| Plan ingestion outputs | Seed-shaped only (features/tasks/enrichment; `prime-context-seed.json` + transform YAML) | Emits **nothing the wireframe can consume** — no projection into manifest space |
| Wireframe inputs | On-disk manifests via convention paths or `--inputs` inventory | No mode that consumes a **pipeline run's** emitted manifests; no linkage to source docs |
| Kickoff docs → manifests | No path at all (verified this session: 0/7 match) | The deterministic extraction phase doesn't exist |
| Acceptance gate | Wireframe is advisory CLI; HITM defines the Customer/PO gate abstractly | No artifact purpose-built for a business walkthrough ("what will be delivered, per iteration") |
| Contract authorship | FR-F3: pipeline never authors `schema.prisma` | Forbids the *kickoff-time drafting* the vision requires (translation ≠ mutation) |

---

## 2. Requirements

### Ingestion side — deterministic manifest emission

- **FR-WPI-1 — Manifest emission artifacts.** Plan ingestion MUST gain a deterministic
  **manifest-extraction phase** that emits the seven assembly manifests
  (`schema.prisma` *draft*, `app.yaml`, `human_inputs.yaml`, `ai_passes.yaml`, `pages.yaml`,
  `completeness.yaml`, `views.yaml`) as run artifacts (`<run-out>/manifests/`), beside the
  existing seed — produced from kickoff docs that conform to the
  [authoring contract](../kickoff/KICKOFF_AUTHORING_CONTRACT.md). Emitted manifests carry
  provenance `extracted` (a tier-G draft state) until human validation promotes them.
  *(Planning: realized as a **sub-step of EMIT orchestration** — `PhaseEmitter._emit_manifests()`
  — not a new phase enum value; requirements docs threaded via one `emit()` signature
  extension.)*
- **FR-WPI-2 — Extraction is deterministic; non-conformance flags, never guesses.** Each
  manifest value derives from a contract-conforming section by parsing — **no LLM call in the
  extraction phase**. A required value with no conforming source section is emitted as
  `not extracted` in the extraction report (FR-WPI-3) and the manifest field is omitted/absent
  — never invented. The remediation loop is upstream: LLM+human co-work *reformats the prose*,
  then re-extracts (the contract's §3 friction loop). **Extraction ordering is a constraint,
  not an implementation choice (CRP R2):** entities/relationships first → views (`Shows:` fk
  values derive from the join models) → completeness (the exclude-line's "connection records"
  maps to the derived join-model names). A single-pass extractor cannot resolve either
  downstream mapping. **Spike-verified grammar rules (F1–F6, empirical):** (i) markdown tables
  segment as *maximal consecutive-`|` runs* — the Pages section legitimately holds two
  adjacent tables (Pages + Nav); naive flattening produced 21 phantom pages (F1); (ii) route
  derivation applies **NFKD normalization** (`Résumé` → `/resume`, never `/r-sum`) (F2);
  (iii) the **Nav table is a route authority** — its targets take precedence over kind-aware
  derivation for views, and entity-UI targets pass through untouched (F6); (iv) `Shows:` lines
  for **detail-compose/workspace are prose, not grammar** — v1 extracts kind/root/route
  **shells** (parser-clean; `ViewSpec` permits empty relations/panels) with `shows` flagged
  `not_extracted`; dashboards' `counts of X per <root>` DO extract to schema-resolved
  aggregates (F3); (v) `Also shows:` / `Empty state:` / `Formats:` have no manifest home —
  flagged `not_extracted`; `Formats:` is a generator-gap (F5).
- **FR-WPI-3 — Extraction report with full traceability.** The phase MUST emit
  `manifest-extraction-report.json` (+ `.md` review form per FR-J2): per manifest, per value —
  `extracted (source: doc §/row/sentence)` | `not extracted (reason)` | `defaulted (source:
  kickoff value file / industry dataset)`. This is the "where did this come from?" currency the
  business walkthrough trades on. **Identity + canonical form (CRP R1 — the report is the
  cross-run diff currency):** value identity = `(manifest filename, canonical value-path)`
  (JSON-pointer style, e.g. `views.yaml#/views/2/route`); source locators are structured
  (`{doc, heading_path, row_index}`), not free prose; entries sorted by identity key; the
  report is **byte-stable** across identical-input runs (renaming an unrelated heading changes
  no value identity).
- **FR-WPI-4 — Schema-valid by construction.** Emitted manifests MUST parse clean through the
  **generators' own parsers** (the same ones the wireframe uses — FR-W3/W14). The extraction
  phase validates its own output by round-tripping it through those parsers before writing; an
  emission that wouldn't survive `generate …` is a bug, not a flag. *(This is what makes the
  strtd8 schema-drift class — three hand-authored manifests invalid on first parser contact —
  structurally impossible for extracted manifests.)* **Two planning caveats:** (a)
  `completeness.yaml` round-trips against the SDK's actual accepted schema (`exclude` +
  `entities.{min_rows,weight}`) — the richer authored fields (nudges, predicates) are flagged
  `not_extracted(generator-gap)`, a visible generator backlog item; (b) `schema.prisma` has no
  writer today — round-trip applies to the six YAML manifests; the contract runs in **DIFF
  mode** (FR-WPI-8); (c) *(sweep 2)* `app.yaml` round-trips against `AppManifest`'s actual
  fields — §2.7's `port`/`env keys`/`sqlite mode` have no manifest home and are flagged
  `not_extracted(generator-gap)`, never emitted as unknown keys (the strtd8 `database`/`env`
  drift class). **Empirically confirmed by the spike:** 4/4 attempted extractions
  (pages/app/views/completeness) from the real strtd8 doc round-tripped clean on first
  contact, with the three generator-gap settings + completeness nudges correctly flagged.
- **FR-WPI-5 — Promotion ratchet (extracted → validated → working).** Emitted manifests land in
  the run dir, not the project tree. A **promotion step** (explicit, human-triggered) copies
  them to the project's conventional paths, flipping provenance `extracted` → `authored` upon
  the owning role's validation (Architect for the contract + conventions-adjacent manifests;
  per the Q1 ratchet). Re-extraction against already-promoted manifests **diffs and flags,
  never overwrites** — authored edits win; the diff is review input for the next co-work pass.

### Wireframe side — run consumption + the acceptance artifact

- **FR-WPI-6 — `--from-run` mode.** `startd8 wireframe --from-run <run-dir|provenance>` MUST
  read the emitted manifests from a plan-ingestion run's `manifests/` dir (instead of project
  conventional paths / `--inputs`), through the **same parsers** (FR-W14 anti-divergence
  preserved unchanged). All existing flags (`--only-issues`, `--json`, `--no-write`) compose.
  Advisory exit semantics (FR-W9) are untouched — the gate is a human act, not an exit code.
  *(Planning: realized at the CLI layer — run-dir manifests map onto the existing flag-style
  overrides. Sweep-2 amendment: the explicit `--from-run` dir is a **second permitted root**
  for FR-W6/R3-F4 path confinement — canonical cap-dev-pipe run dirs live outside the consumer
  project root, embedded runs inside; confinement is otherwise unchanged. `--from-run` composes
  with `--project`, which remains the app root for content-inputs file checks.)*
  **Confinement mechanics (CRP R1/R2 — the sweep-2 intent, now specified):** (i) the allowance
  is **origin-keyed** — it applies only to entries the `--from-run` mapping itself synthesizes,
  never to `--inputs`-file or other flag paths even when they point under the run dir; (ii)
  comparison is **fully-resolved paths against the fully-resolved `extra_root`** (a symlink
  inside the run dir escaping both roots ⇒ exit 2); (iii) **advisory checks, never gates** —
  warn when the run's provenance project identity ≠ `--project` (stale/foreign run ⇒ plausible
  but wrong walkthrough) and when the run dir is world-writable or not owned by the invoker (a
  poisoned shared dir is a manifest-injection point into the acceptance artifact); (iv) a
  `*.json` provenance argument resolves via its `output_dir` field to the same `manifests/`
  dir.
- **FR-WPI-7 — End-to-end fingerprint linkage.** The wireframe plan (FR-W12's persisted
  artifact) MUST, in `--from-run` mode, record: source kickoff-doc checksums (from the run's
  `context_files`), the extraction-report hash, per-manifest hashes, and the seed checksum — so
  the acceptance artifact is traceable **prose → extraction → manifest → wireframe**, and a
  later `wireframe --diff` (OQ-8 of the base spec) can answer "did we deliver what they walked
  through?" **Hash semantics (CRP R2):** per-manifest hashes hash the **parsed canonical model**
  (deterministically serialized), not raw YAML bytes — a key-order reformat never changes them;
  `run_linkage.run_dir` records the **resolved canonical path** (a `current/` symlink and its
  target fingerprint identically); `source_doc_checksums` and `seed_checksum` are
  **provenance-only** fields (the seed is LLM-path output that churns on identical inputs) —
  neither participates in the FR-WPI-10 re-walk trigger.
- **FR-WPI-9 — Per-phase delivery inventory (the walkthrough artifact).** The wireframe MUST
  render (additively to the existing tree) a **delivery inventory grouped by iteration phase**
  — ① framework+persistence (entities, CRUD, scaffold), ② display+business logic (pages, nav,
  views, completeness), ③ integration+content (AI passes, prompts, prose) — using a **static
  kind→iteration mapping** (planning correction: manifests carry no phase tags today and don't
  need them). Per phase: what will be delivered, its status, and its source-doc citation
  (FR-WPI-3/7). Rendered in the terminal tree, `--json`, and the existing
  `wireframe-summary.md` form (shareable with non-terminal business users). This is the lo-fi
  prototype the business user walks per iteration — and re-walks before each prime-contractor
  iteration starts.

### Gate & governance

- **FR-WPI-10 — The acceptance gate (HITM-wired, advisory-mechanical).** The business
  walkthrough of the FR-WPI-9 inventory is the **Customer/PO validation point** (HITM §3.0)
  for "what is to be built," evaluated **before the prime contractor consumes the run**
  (hash-bound per FR-J3: acceptance binds to the wireframe-plan fingerprint; re-walks trigger
  only when the fingerprint changes). **Trigger scope (CRP R1/R2 — so the gate is never
  ceremony):** the re-walk fingerprint binds to the **stable provenance slice only** — the
  per-manifest *semantic* hashes + the extraction-report value-set hash (FR-WPI-7) — never the
  whole plan artifact (which carries per-invocation rendering metadata) and never the
  provenance-only fields (`source_doc_checksums`, `seed_checksum`). A typo in never-extracted
  prose, an LLM-seed churn, or a YAML reformat does NOT re-open the gate; editing a pages-table
  row does. Recording is **operator-coordinated** (the Q2 decision —
  no approval store is built); cap-dev-pipe ordering is: ingestion → wireframe → *operator
  confirms walkthrough* → prime contractor; unattended runs record the standard
  `unattended-override`, never a synthesized acceptance. *(Planning: the invocation point
  already exists — the `STARTD8_WIREFRAME=1` hook runs post-ingestion/pre-prime at
  `run-prime-contractor.sh:212`; this FR adds only the `--from-run` wiring + the
  operator-confirm ordering documentation.)*
- **FR-WPI-11 — Controlled-corpus alignment (advisory until the corpus ships).** The
  extraction phase is a **corpus producer and consumer**: (a) it consults corpus synonyms for
  surface-form canonicalization (flag, never auto-merge, on low confidence); (b) every clean
  extraction + FR-WPI-4 round-trip emits a determinism sample for the term bindings involved
  (term → manifest construct), feeding corpus recurrence/confidence at postmortem — the corpus
  doc's established production point; (c) the authoring-contract vocabularies it parses against
  are corpus-versioned (contract §4b). No accumulation machinery is built here — the corpus
  owns that; this FR only keeps the two from diverging.
- **FR-WPI-8 — FR-F3 amendment (drafting ≠ mutation).** Kickoff-time **contract drafting** by
  the extraction phase (emitting a `schema.prisma` *draft* into the run dir, Architect-validated
  before promotion) is permitted and is the intended path — extending the Q1
  generated→validated→reused ratchet to the contract. FR-F3's prohibition is **rescoped to the
  project tree and to mid-run mutation**: no pipeline stage ever writes the *promoted* contract
  path, and the VALIDATE hash check stands. The bookend is preserved — human leverage moves
  from "writes Prisma" to "validates Prisma against their own prose."
  *(Planning: two modes — **DIFF** (existing contract: entity tables vs live `.prisma` → drift
  report; the strtd8 pilot path, buildable now) and **DRAFT** (greenfield; requires the Prisma
  emitter that exists nowhere in the codebase — deferred to plan P7).)*

---

## 3. Non-Requirements

- **No LLM anywhere in extraction or wireframe** — the LLM spend stays upstream, in the
  co-work that reaches the authoring contract.
- **No gating exit codes** — the wireframe stays advisory (FR-W9); the gate is the recorded
  human act + pipeline ordering, never a CLI failure.
- **No seed-schema coupling** — the wireframe never reads `prime-context-seed.json`; manifests
  remain the only interface (one projection, one set of parsers).
- **No auto-promotion** — emitted manifests never silently become the project's working
  manifests (FR-WPI-5's human trigger is load-bearing).
- **No hi-fi prototype** — the walkthrough artifact is the wireframe's tree/inventory, not
  rendered HTML pages.
- **Does not replace the seed/prime-contractor path** — manifest emission is a *second
  projection* of the same kickoff docs, additive to the existing EMIT.

---

## 4. Acceptance Snapshot (strtd8 MVP as the pilot)

> **Spike evidence (2026-06-05): the wireframe-side acceptance below is already demonstrated**
> — extracted pages/app/views/completeness + the real contract produced `ready`×3, 16 entities
> / 80 CRUD routes, `Target Roles` in nav, `Metric.value` owned-omitted, at $0
> (`spike-2026-06-05/`). What remains for P6 is producing the same result through the
> *shipped* path (ingestion EMIT → `--from-run` → report citations), not proving feasibility.

> **The pilot is now a standing customer request** —
> `strtd8/docs/kickoff/VALIDATION_AND_MANIFEST_DERIVATION.md` (2026-06-05): the team adopted
> the format as their standard, **requests the three INVALID manifests be derived from
> REQUIREMENTS/PLAN rather than hand-fixed** (`app.yaml` ← the new "Scaffold & runtime"
> section; `pages.yaml` ← Pages; `views.yaml` ← Views), and declares the hand-persisted
> manifests *superseded inputs* once derivation lands (already-invalid, so FR-WPI-5's
> authored-wins diff rule has no conflict — these retire). Their concrete acceptance, all
> checkable at $0: `startd8 wireframe --only-issues` until `scaffold|backend|views: ready`;
> **16 entities / 80 CRUD routes**; nav includes **Target Roles** after Profile;
> `COST_BUDGET_USD` default **10.00** (the authored budget — `5.00` is stale); FR-6
> owned-field omissions reach every generated form. Their open derivation question (view
> routes) is **answered in the authoring contract §2.3**: kind-aware derivation + optional
> explicit `Route:` override.

- Authoring-contract-conformant sections added to the strtd8 kickoff docs → one ingestion run
  emits all seven manifests, parser-clean (FR-WPI-4), with an extraction report tracing every
  value to a doc section.
- `startd8 wireframe --from-run <run>` renders the same 15-entity shape as today's
  manifest-based run, plus the per-phase delivery inventory; fingerprints chain back to the
  kickoff docs.
- The operator walks the inventory as Customer/PO, confirms, promotes the manifests, and the
  prime contractor's iteration ① starts from validated inputs — with zero LLM calls spent
  between prose and walkthrough.
- A deliberately malformed pages section yields `not extracted` + a report pointer — never an
  invented route.

---

## 5. Open Questions — ALL RESOLVED (planning pass, 2026-06-05)

1. ~~**OQ-1 — Emission home.**~~ **RESOLVED:** a sub-step of EMIT orchestration
   (`PhaseEmitter._emit_manifests()`); phases are sequential in-memory — no checkpoint
   interaction, no phase-enum change.
2. ~~**OQ-2 — Partial conformance.**~~ **RESOLVED: yes, emit partial — at manifest-ENTRY
   granularity (CRP R1).** An entry missing a parser-required key is dropped + reported
   `not_extracted`; the manifest still emits with ≥1 valid entry; zero valid entries ⇒ skip
   emission entirely (parsers loud-fail on empty lists) and statuses fall back to
   absent-manifest handling. `--only-issues` is the remediation worklist.
3. ~~**OQ-3 — Promotion mechanics.**~~ **RESOLVED:** documented manual copy + inventory status
   flip (`extracted` → `authored`) per the Q2/Q5 operator-coordinated spirit; the `assist`
   drift check owns ongoing divergence; a `promote-manifests` subcommand is a follow-up.
4. ~~**OQ-4 — Draft vs diff for the contract.**~~ **RESOLVED:** DIFF mode for strtd8 (drift
   report vs the live contract); DRAFT mode is greenfield-only and deferred with the P7 Prisma
   emitter.
5. ~~**OQ-5 — Walkthrough rendering.**~~ **RESOLVED: both** — terminal tree + the pipeline
   shim's existing `wireframe-summary.md` writer reused as the shareable form; `--json` for
   machines.

---

## 6. Planning-Pass Checklist — ALL VERIFIED (2026-06-05; details in §0 + the paired plan)

- [x] Emitter artifact seam — clean/additive (`artifacts_out` + `atomic_write_json`,
      `plan_ingestion_emitter.py:845–931`); no checkpoint interaction
- [x] Wireframe run-dir source — CLI-level override mapping; `inputs.py` untouched
- [x] Generator parsers importable, no circular deps — the wireframe already imports exactly
      these (`wireframe/plan.py:19–29`)
- [x] Phase tags — none exist; static kind→iteration map suffices (FR-WPI-9 corrected)
- [x] Grammars parseable stdlib-only — section/list parsers exist; one small md-table parser
      to add (P0)
- [x] cap-dev-pipe hook — already post-ingestion/pre-prime (`run-prime-contractor.sh:212`)

---

*v0.2 — Post-planning self-reflective update: 8 assumptions tested (2 falsified, 4 narrowed),
all 5 OQs resolved, FR-WPI-8 split into DIFF (pilot) / DRAFT (deferred P7) modes, one new
vocabulary-drift discovery (completeness schema — flagged as generator backlog). Paired plan
v1.0 (P0–P7). Next per the loop: CRP offer, then implement.*

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
| R1-F1 | ExtractionReport identity + canonical/byte-stable form | R1 (opus); endorsed R2 | FR-WPI-3 identity clause (JSON-pointer paths, structured locators, sorted) | 2026-06-05 |
| R1-F2 | Re-walk trigger scoped to extraction-relevant content | R1 (opus); endorsed R2 | FR-WPI-10 trigger-scope clause; doc checksums provenance-only (FR-WPI-7) | 2026-06-05 |
| R1-F3 | `extra_root` origin-keying, resolved-path semantics, foreign-run advisory | R1 (opus); endorsed R2 | FR-WPI-6 confinement-mechanics block | 2026-06-05 |
| R1-F4 | Partial-conformance = manifest-entry granularity; snapshot-mark restated vocab | R1 (opus); endorsed R2 | §5 OQ-2 resolution rewritten; §0 tables note contract ownership (contract §5) | 2026-06-05 |
| R2-F1 | Nav targets = opaque route strings; advisory render status | R2 (sonnet) | Contract §2.2 nav rule; wireframe renders "route not in manifest" advisory | 2026-06-05 |
| R2-F2 | View-heading annotation stripping stated for both heading forms | R2 (sonnet) | Landed in contract §2.0 (View:-prefix rule); FR-WPI-4 inherits via the contract | 2026-06-05 |
| R2-F3 | `run_linkage.run_dir` records the resolved canonical path | R2 (sonnet) | FR-WPI-7 hash-semantics clause | 2026-06-05 |
| R2-F4 | Per-manifest hashes = parsed canonical model, not YAML bytes | R2 (sonnet) | FR-WPI-7 hash-semantics clause | 2026-06-05 |
| R2-F5 | Extraction ordering constraint (relationships → views → completeness) | R2 (sonnet, adversarial) | FR-WPI-2 ordering clause; contract §2.3/§2.4 sequencing notes | 2026-06-05 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-05

- **Reviewer**: Claude Opus 4.8 (claude-opus-4-8-1m)
- **Date**: 2026-06-05 23:23:38 UTC
- **Scope**: Dual-doc + authoring-contract review per `crp-focus-wiring-grammars.md`; grammars tested against the strtd8 worked instance (`REQUIREMENTS_v0.5-draft.md`); parsers spot-verified read-only (`view_codegen/manifest.py`, `scaffold_codegen/manifest.py`, `pages_generator.py`, `ai_layer.py`, `derived.py`, `wireframe/inputs.py`).

##### Focus-ask answers

**Ask 1 — Grammar ambiguity hunt.**
- **Summary answer:** Yes — seven concrete divergence points where two extractor implementers would differ; the worst is relationship-verb drift (`links to many` and `date+time` are taught by the templates and used by the pilot doc, but absent from contract §2.1's closed sets).
- **Rationale:** Tested contract §2 against the worked instance: it uses `**links to many**` (ProofPoint/Capability/Outcome blocks) and even "links Capability **to** nothing (plain link)" — neither in the §2.1 closed set (has one / has many / belongs to / links X to Y); `REQUIREMENTS_TEMPLATE.md:57–58` teaches `links to many` and `date+time` as if contractual. Views blocks in the instance use `Also shows`/`Of`/`Formats`/`Gap callout`/`Empty state` — §2.3 says "constrained keys" but never enumerates them, and `parse_views` (`view_codegen/manifest.py:22–31`) accepts none of those surface names; the `Shows: A→B (annotation)` line has no defined mapping to the required `relations{name,from,fk}` sub-schema. Other holes: plural entity refs ("at least 3 ProofPoints", "has many ProofPoints") with no singularization rule; heading annotations (`### TargetRole *(added 2026-06-05 …)*`) with no stripping rule; the two-fields-one-row AiCall cell (`promptTokens / responseTokens`); the §2.7 `env keys` cell micro-syntax (`KEY (qualifier — prose) · KEY (…)`); unicode/kebab/reserved-name rules (Résumé, `metadata`) absent.
- **Assumptions / conditions:** the strtd8 v0.5 draft is treated as representative conforming authoring (the team adopted the format), so where it and the contract disagree, the contract — not the instance — needs the fix.
- **Suggested improvements:** R1-G1–R1-G5 in `KICKOFF_AUTHORING_CONTRACT.md` Appendix C propose the specific tightenings (closed-set completion + 3-entity join semantics, published type-mapping table, per-kind view key enumeration + Shows micro-grammar + block-termination rule, name-derivation rules, §2.7 mapping table).

**Ask 2 — Cross-doc single-source drift.**
- **Summary answer:** Yes — three live drift instances confirmed beyond the five on record, all in the templates; the contract should be declared the single owner of every §2 vocabulary/grammar, with templates and wiring docs citing §-refs only.
- **Rationale:** (a) relationship verbs: contract §2.1 lists 4; `REQUIREMENTS_TEMPLATE.md:58` and `HOW_TO_AUTHOR_REQUIREMENTS_AND_PLANS.md:71` list 5 (adding `links to many`); (b) plain types: template `:57` adds `date+time`, absent from §2.1; (c) completeness: template `:101` teaches an "and a nudge" suffix the contract §2.4 grammar omits and the SDK cannot represent (`derived.py` accepts only `exclude` + `entities.{min_rows,weight}`) — the format actively instructs authors to write a generator-gap field. Also duplicated as restatements (divergence-capable): view-route derivation (contract §2.3 / template `:95` / plan P1 views row), §2.7 settings vocabulary (contract / template `:45–46` / this doc's sweep-2 row), completeness grammar (contract §2.4 / template `:101` / FR-WPI-4(a)).
- **Assumptions / conditions:** templates remain "context-only" teaching surfaces — they may show worked examples, but vocab *lists* are quotations of the contract, marked as such.
- **Suggested improvements:** R1-G6 (ownership note + resolve the two vocabulary deltas + the nudge decision) in the contract; R1-F4 below keeps this doc's own restatements snapshot-marked.

**Ask 3 — `extra_root` confinement relaxation.**
- **Summary answer:** Sound trust basis (explicit operator flag), but underspecified on four points: symlink/resolution order, origin-keyed scoping, foreign/stale run-dir detection, and what the run dir can make the wireframe read.
- **Rationale:** `_confine` (`inputs.py:78–81`) `.resolve()`s before the prefix check, so a symlink inside the run dir escaping both roots IS rejected — but only if the implementation (i) resolves `extra_root` itself before comparison and (ii) checks "resolved path under resolved root", which no requirement currently states. The amendment text says flag paths and `--inputs` keep single-root semantics, but nothing forces the allowance to be *origin-keyed* (applied only to the entries the `--from-run` CLI mapping synthesizes) rather than a global second root an `--inputs` entry could ride. A hostile/wrong `--from-run` is read-only blast radius (wireframe writes only its own plan artifact), but a *stale or foreign* run dir silently produces a plausible walkthrough — nothing binds the run to the project. Exit-2-on-violation is consistent with FR-W9 (input errors were already fatal; advisory applies to findings, not unreadable inputs).
- **Assumptions / conditions:** manifest-referenced content files keep being checked against `--project` root only (stated in FR-WPI-6) — that must hold or the run dir gains read reach.
- **Suggested improvements:** R1-F3 below; plan-side test additions R1-S3.

**Ask 4 — Report + fingerprint semantics.**
- **Summary answer:** (a) No — `ExtractionReport` per-value identity is not defined tightly enough for stable cross-run diffing; (b) Yes — whole-doc `source_doc_checksums` re-opens the gate on any prose typo, making the FR-J3 binding ceremony.
- **Rationale:** FR-WPI-3 defines the three value *states* but no stable identity key, no canonical ordering, and `source: doc §/row/sentence` as free prose — two runs over identical inputs could legally emit differently-ordered, differently-worded reports, and a renamed unrelated heading can shift "§" references. FR-WPI-7 records whole-doc checksums; FR-WPI-10 binds re-walks to the wireframe-plan fingerprint which includes them — so a typo in never-extracted prose changes the fingerprint and re-triggers the walkthrough even though every manifest byte is identical.
- **Assumptions / conditions:** the run already computes per-manifest hashes and the extraction-report hash (FR-WPI-7) — the cheaper binding below reuses them, no new machinery.
- **Suggested improvements:** R1-F1 (identity = `(manifest, canonical value-path)` + structured source locator + sorted emission, byte-stable); R1-F2 (re-walk trigger binds to per-manifest hashes + extraction-report *value-set* hash; doc checksums stay recorded as provenance but are excluded from the trigger — the extraction-relevant-content scoping, FR-J3 lazy-rule analog).

##### Executive summary

- The contract's closed vocabularies are already forked: templates teach `links to many` and `date+time`, the pilot doc uses them, the contract omits them — extraction built to §2.1 alone will flag the reference consumer's conforming-in-spirit doc all over.
- §2.3's "every other line maps 1:1" is false today: `Shows:`/`Empty state`/`Of:`/`Formats:` have no defined mapping to `parse_views`' required sub-schemas; this is the highest-ambiguity grammar.
- `ExtractionReport` needs an identity/ordering contract before it can be the cross-run diff currency FR-WPI-3 wants it to be.
- FR-WPI-10's gate re-opens on cosmetic prose edits as written — scope the trigger to extraction-relevant content.
- The `extra_root` allowance needs origin-keying and resolved-path semantics spelled out; otherwise correct-by-luck.
- Completeness round-trip is vacuous: the tolerant loader accepts any mapping, so FR-WPI-4(a)'s guarantee needs an emission-side strict check (plan-side R1-S2).
- FR-WPI-11's two active behaviors (synonym consultation, determinism-sample emission) have no plan home — only the corpus-snapshot field landed in P0.

##### Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Data | high | Define `ExtractionReport` per-value identity and canonical form: identity key = `(manifest filename, canonical value-path)` (JSON-pointer-style, e.g. `views.yaml#/views/2/route`); source locator structured (`{doc, heading_path, row_index}`) not free prose; entries sorted by identity key; report byte-stable across identical-input runs | FR-WPI-3's "per manifest, per value — `extracted (source: doc §/row/sentence)`" leaves identity, ordering, and locator form to the implementer — cross-run diffing (the FR-WPI-7/OQ-8 use case) breaks on incidental ordering or wording differences | FR-WPI-3, new sentence after the state enumeration | Two runs on identical inputs → byte-identical reports; rename an unrelated heading → no value-identity changes |
| R1-F2 | Risks | high | Scope FR-WPI-10's re-walk trigger to extraction-relevant content: the gate fingerprint binds to per-manifest hashes + the extraction-report value-set hash (both already in FR-WPI-7's `run_linkage`); whole-doc `source_doc_checksums` remain recorded as provenance but are excluded from the re-walk trigger | As written, "re-walks trigger only when the fingerprint changes" + doc checksums in the fingerprint means a typo in never-extracted prose re-opens the Customer/PO gate — ceremony that trains operators to rubber-stamp re-walks | FR-WPI-10, the hash-bound clause; cross-ref FR-WPI-7 | Test: edit free prose the extraction ignores, re-run ingestion → manifests byte-identical, gate stays closed; edit a pages-table row → gate re-opens |
| R1-F3 | Security | high | Tighten FR-WPI-6's second-root amendment: (i) allowance is origin-keyed — applies only to the manifest entries the `--from-run` CLI mapping itself synthesizes, never to `--inputs`-file or other flag paths even when those happen to point under the run dir; (ii) confinement compares fully-resolved paths against the fully-resolved `extra_root` (symlink inside the run dir escaping both roots → exit 2); (iii) advisory foreign-run check: warn when the run's provenance/project identity doesn't match `--project` | The sweep-2 amendment states intent ("flag paths and `--inputs` files keep single-root semantics") but not the mechanism; `_confine` (`inputs.py:78–81`) resolves symlinks correctly only if `extra_root` is itself resolved pre-comparison; nothing detects a stale/foreign run dir producing a plausible-but-wrong walkthrough | FR-WPI-6, the sweep-2 amendment parenthetical | Tests: symlinked manifest escaping both roots exits 2; `--inputs` file under the run dir but outside project root exits 2; mismatched-project run dir emits the advisory warning |
| R1-F4 | Interfaces | medium | Specify partial-conformance granularity for OQ-2's "emit partial": the unit is the manifest *entry* — an entry missing a parser-required key (e.g. a Views block with no derivable `kind`) is dropped and reported `not_extracted`, the manifest still emits if ≥1 valid entry remains; zero valid entries ⇒ skip emission entirely (parsers like `parse_pages` loud-fail on empty lists), statuses fall back to the wireframe's absent-manifest handling. Also mark this doc's restated vocab lists (§0 sweep tables) as contract-§ snapshots, non-normative | "Emit what conforms" is currently ambiguous between file-, entry-, and field-level granularity, and the round-trip requirement (FR-WPI-4) makes the wrong choice fail loud in production rather than at design time | OQ-2 resolution text in §0/§5; FR-WPI-4 | Fixture: one malformed view among four → manifest emits 3 entries + 1 `not_extracted`; all-malformed → no `views.yaml`, report explains |

##### Endorsements & Disagreements

None — both wiring docs' Appendix C were empty before this round (first review).

#### Review Round R2 — claude-sonnet-4-6 — 2026-06-06

- **Reviewer**: claude-sonnet-4-6
- **Date**: 2026-06-06 00:00:00 UTC
- **Scope**: Dual-doc + authoring-contract review R2 (Feature Requirements side); second-order effects of R1 findings; adversarial grammar pass on the worked instance (`REQUIREMENTS_v0.5-draft.md`); focus-ask extensions where R1's answers were partial.

##### Focus-ask answers (extensions only — concur with R1 where noted)

**Ask 1 — Grammar ambiguity (extensions to R1's answer).**
- **Summary answer:** R1 identified seven divergence points; two additional ones confirmed: (1) view-block annotated headings (`### View: Job Workspace *(P2 preview)*`) — R1-G4 defines heading-annotation stripping for entities but §2.3 makes no parallel statement for views; (2) the Nav table's `Target` column accepts routes like `/ui/proofpoint` and `/value-map` that are neither page-derived slugs nor view-derived routes — the contract never states whether nav targets are free strings or validated against the known route set.
- **Rationale:** The worked instance's Nav table (`REQUIREMENTS_v0.5-draft.md:280–298`) has 17 nav rows with targets like `/ui/targetrole`, `/completeness`, `/export/resume` — none derivable from the pages table's three rows or the four view blocks. The contract §2.2 says "an optional Nav table overrides when nav ≠ pages" but is silent on whether targets are validated. Two implementers would differ: one emits the targets verbatim (string pass-through); the other validates against a known route set and flags unknowns. R1-G4's annotation-stripping rule applies to `### EntityName *(…)*` but view headings are `### View: Name *(…)*` — the colon-prefixed form is a different parse.
- **Assumptions / conditions:** The Nav table's `/ui/…` routes are CRUD paths the backend codegen generates — they exist at runtime but don't appear in the pages or views manifests; the contract was written before this coupling was explicit.
- **Suggested improvements:** R2-F1, R2-F2 below.

**Ask 3 — `extra_root` confinement (extension).**
- **Summary answer:** Concur with R1. One additional attack vector: `--from-run` resolves the run dir before calling `_confine`, but if the run dir itself is a symlink (a common cap-dev-pipe pattern for `current/` → `run-20260605/`), the resolved path comparison is correct, but the `extra_root` recorded in the audit trail / provenance is the symlink path, not the canonical path — the two are inconsistent for diff/fingerprint comparison.
- **Suggested improvements:** R2-F3 below.

**Ask 4 — Report + fingerprint semantics (extensions).**
- **Summary answer:** Concur with R1 on (a) and (b). Extension: FR-WPI-7 says "per-manifest hashes" but doesn't specify whether these hash the emitted YAML content or the parsed model — if they hash the YAML bytes, a reformatting (e.g. `yaml.safe_dump` key-order change) changes the hash without changing the manifest's semantic content.
- **Suggested improvements:** R2-F4 below (hash the parsed+canonical form, not the raw YAML bytes).

##### Executive summary

- The Nav table's target column is free-string by default — the contract gives no validation rule, so nav entries pointing at CRUD routes (not in pages/views manifests) silently pass extraction as opaque strings, but the wireframe cannot verify they resolve.
- View-block heading annotation stripping is undefined: `### View: Job Workspace *(P2 preview)*` is in the worked instance; R1-G4's rule covers entity headings only.
- FR-WPI-7 hashes the raw YAML output — reformatting without semantic change alters the fingerprint, creating phantom re-walk triggers that survive R1-F2's fix.
- The `extra_root` symlink-path vs canonical-path inconsistency in the audit trail is a low-severity but confusing traceability gap.

##### Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | Interfaces | high | Specify Nav-table target validation rule: nav targets are treated as **opaque route strings** (free-form, not validated against the known page/view route set) — extraction emits them verbatim, the wireframe's existing unknown-route flagging handles resolution at render time. State this explicitly to prevent implementers from validating (and falsely flagging) legitimate CRUD routes like `/ui/proofpoint` that exist at runtime but aren't in the pages/views manifests. Cross-ref: the worked instance has 17 nav rows, only 3 match pages + 4 match views; the other 10 are CRUD/export routes that are valid but invisible to the extraction phase. | "An optional Nav table overrides when nav ≠ pages" is silent on whether targets are validated; an implementer who validates against the known route set would flag 10 of 17 nav entries in the strtd8 pilot as `not_extracted` — breaking the §4 acceptance criterion "nav includes Target Roles after Profile" | FR-WPI-6 / FR-WPI-9 (the wireframe rendering step); KICKOFF_AUTHORING_CONTRACT.md §2.2 | Fixture: Nav table with `/ui/proofpoint` target → emitted verbatim, not flagged; wireframe renders the nav entry with status "route not in manifest" (advisory, not absent) |
| R2-F2 | Interfaces | medium | Clarify view-block heading annotation stripping in FR-WPI-1/FR-WPI-4: the rule that strips ` *(…)*` from entity headings (R1-G4) applies equally to view headings — `### View: Job Workspace *(P2 preview)*` extracts as view name "Job Workspace". The view-name grammar (`### View: <name>`) strips the `View: ` prefix and then applies the annotation-stripping rule. State this parallel explicitly; without it, the P2-preview annotation either errors the parser or produces a view named "Job Workspace *(P2 preview)*" with a wrong derived route. | The worked instance has four view blocks: one is `### View: Value Map` (clean), three have `*(P2 preview)*` annotations; R1-G4 only states the entity-heading rule; the contract's §2.3 worked example is annotation-free. Confirmation: `parse_views` keys on the `name` field which is populated by the extractor, not the markdown — so the extractor is responsible for the stripping, not the parser. | FR-WPI-1 (or as a note in FR-WPI-4's §2.3 cross-ref); KICKOFF_AUTHORING_CONTRACT.md §2.3 | Fixture: `### View: Job Workspace *(P2 preview)*` → name="Job Workspace", route derived as `/job-workspace`; *(P2 preview)* not in route |
| R2-F3 | Data | low | FR-WPI-7 fingerprint audit trail: when `--from-run <symlink-dir>`, record the **resolved** (canonical) path in `run_linkage.run_dir`, not the symlink path — so that two invocations using different symlinks pointing at the same run dir produce identical `run_linkage` entries and fingerprints. Applies to the provenance-file case (R2-S1) as well: the provenance's `output_dir` field may be a non-canonical path from a prior run. | "Run dir" in the audit trail is used to answer "did I walk through what I delivered?" — a fingerprint that differs between `current/` and `run-20260605/` (same content) breaks that cross-run comparison for no reason; the resolved path is the stable identity. | FR-WPI-7 (`run_linkage` sub-object definition) | Test: two `--from-run` invocations via different symlinks to the same run dir → identical `run_linkage.run_dir` values |
| R2-F4 | Data | medium | FR-WPI-7: specify that per-manifest hashes in `run_linkage` hash the **parsed canonical model** (the generator's parsed struct, serialized deterministically), not the raw YAML bytes — so that YAML reformatting (key-order change, trailing-newline difference) does not change the hash without changing manifest content. This is the same stability guarantee R1-F1 requires for the ExtractionReport: byte-stable over identical semantic inputs. | P3 says `schema_version` stays 1 and additions are additive — a yaml.safe_dump key-order change in a future version would change all per-manifest hashes and re-open every acceptance gate, even though every extractor output is semantically identical. The re-walk trigger (R1-F2) binds to per-manifest hashes; they must be semantic hashes, not format hashes. | FR-WPI-7 (the `run_linkage` definition paragraph) | Test: emit a manifest, reformat the YAML with different key order, re-hash → same value |

##### Stress-test / adversarial pass

Testing the worked instance (`REQUIREMENTS_v0.5-draft.md`) against contract §2 grammars as an adversarial extractor implementer:

**Relationship sentence dedup failure:** the worked instance has all three pairs stated symmetrically — `ProofPoint links to many Capabilities`, `ProofPoint links to many Outcomes`, `Capability links to many ProofPoints`, `Capability links to many Outcomes`, `Outcome links to many ProofPoints`, `Outcome links to many Capabilities`. Without the R1-G1 dedup rule, an implementer following the closed set `has one / has many / belongs to / links X to Y` literally would see `links to many` as outside the set and flag *all six sentences* `not_extracted` — meaning the §4 acceptance criterion "16 entities / 80 CRUD routes" (which includes the 3 join tables) would fail entirely. This confirms R1-G1 is load-bearing for the pilot to pass, not just a nice-to-have.

**"Connection records" exclude ambiguity:** the worked instance's Completeness section reads `(Don't count: connection records, AiCall)`. An implementer builds the exclude list as `["connection records", "AiCall"]` — but the SDK's `completeness.yaml` exclude field takes entity names. "Connection records" is not an entity name; the three join models are unnamed at authoring time (they're derived from the relationship sentences). An extractor without R1-G6's category-word mapping has no way to resolve "connection records" to the three join model names. This is a second-order effect of R1-G6 + R1-G1 interacting: if the join model names aren't known until R1-G1's dedup rule runs, the exclude mapping must happen after relationship extraction, not in a single pass.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F5 | Data | high | FR-WPI-1/FR-WPI-2: require that the extractor processes relationship sentences **before** completeness sentences — the exclude-line's "connection records" category maps to join model names that are only known after the entity/relationship extraction pass. Add a note to FR-WPI-2 that extraction order within a run is: entities (fields + relationships) → completeness (exclude mapping uses derived join model names). This is a sequencing constraint, not an implementation choice. | The worked instance has `(Don't count: connection records, AiCall)` — "connection records" cannot resolve to `[ProofPointCapability, ProofPointOutcome, CapabilityOutcome]` without first knowing the three join models derived from the relationship sentences; a single-pass extractor that reaches completeness before relationships has no names to map | FR-WPI-2 (extraction is deterministic) — add an ordering note; FR-WPI-1 (manifest emission) | Fixture: completeness exclude "connection records" → after relationship extraction, maps to the three derived join model names in the emitted `completeness.yaml` exclude list |

##### Endorsements & Disagreements

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R1-F1: ExtractionReport identity + canonical form — endorsing; the adversarial pass confirms that symmetric relationship restatements create ordering ambiguity in the report if identity is undefined.
- R1-F2: Re-walk trigger scoped to extraction-relevant content — endorsing; R2-F4 extends the same principle to per-manifest hash semantics.
- R1-F3: `extra_root` origin-keying and resolved-path semantics — endorsing; confirmed by reading `_confine` behavior.
- R1-F4: Partial-conformance granularity at the entry level — endorsing; the adversarial pass on the worked instance confirms that "all-malformed views → no views.yaml" is the correct behavior, not "extract what we can from malformed entries".
